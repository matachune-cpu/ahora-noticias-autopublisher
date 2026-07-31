"""
Publica una nota específica por URL externa al pipeline automático.

Uso:
    python _publicar_url.py <url> [--fuente "Nombre Fuente"]

Ejemplo:
    python _publicar_url.py https://nuevodiarioweb.com.ar/policiales/... --fuente "Nuevo Diario"

Pasos:
    1. Extrae el artículo de la URL indicada
    2. Reescribe con Gemini
    3. Sube imagen a WordPress (o busca en Google si no hay imagen propia)
    4. Publica en WordPress
    5. Publica en Facebook
    6. Genera flyer y publica en Instagram (directo, sin encolar)
    7. Registra en la base de datos
"""
import argparse
import logging
import os
import sys
import tempfile
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import config
import database
from scraper import extract_article
from rewriter import rewrite_article, check_watermark
from flyer_generator import generate_flyer
from image_search import search_image
from publishers import wordpress, facebook, instagram, whatsapp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("publicar_url")


def publicar(url: str, fuente: str):
    database.init_db()

    logger.info(f"━━━━ Publicando: {url}")
    logger.info(f"      Fuente: {fuente}")

    # 1. Verificar si ya fue publicada
    if database.is_published(url):
        logger.warning("Esta URL ya fue publicada anteriormente. Abortando.")
        sys.exit(0)

    # 2. Extraer artículo
    article = extract_article(url, source_name=fuente, title="", summary="")
    if not article:
        logger.error("No se pudo extraer contenido del artículo. Abortando.")
        sys.exit(1)
    logger.info(f"Título extraído: {article.title[:80]}")

    # 3. Reescribir con Gemini
    rewritten = rewrite_article(article.title, article.full_text, fuente)
    if not rewritten.get("es_publicable"):
        logger.error("Gemini rechazó el contenido. Abortando.")
        sys.exit(1)
    logger.info(f"Título reescrito: {rewritten['title'][:80]}")

    # 4. Imagen: verificar marca de agua → fallback a Google Images
    imagen = article.image_url
    if imagen:
        if check_watermark(imagen):
            logger.info(f"Imagen descartada por marca de agua: {imagen}")
            imagen = None
    if not imagen:
        imagen = search_image(rewritten["title"])
        if imagen:
            logger.info(f"Imagen de Google: {imagen[:100]}")
        else:
            logger.info("Sin imagen disponible (ni propia ni de Google)")

    # 5. Subir imagen a WordPress
    media_id = None
    media_url = None
    if imagen:
        media_id, media_url = wordpress.upload_image(
            image_url=imagen,
            filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        )

    # 6. Publicar en WordPress
    wp_post_id, wp_post_url = wordpress.create_post(
        title=rewritten["title"],
        body_html=rewritten["body_html"],
        original_url=url,
        source_name=fuente,
        featured_media_id=media_id,
    )
    if not wp_post_id:
        logger.error("WordPress falló. Abortando publicación en redes.")
        database.mark_seen(url, rewritten["title"], fuente)
        sys.exit(1)
    logger.info(f"WordPress: post creado → {wp_post_url}")

    # 7. Publicar en Facebook
    fb_post_id = facebook.post_link(
        title=rewritten["title"],
        wp_post_url=wp_post_url,
        original_url=url,
        image_url=media_url or imagen,
    )
    logger.info(f"Facebook: {'OK ID=' + str(fb_post_id) if fb_post_id else 'FALLÓ'}")

    # 8. Generar flyer y publicar en Instagram (directo, sin encolar)
    ig_post_id = None
    flyer_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name
        generate_flyer(
            title=rewritten["title"],
            source_name=fuente,
            article_image_url=imagen,
            template_path=config.FLYER_TEMPLATE_PATH,
            output_path=flyer_path,
            categoria=rewritten.get("categoria", ""),
        )
        _, flyer_url = wordpress.upload_image(
            image_path=flyer_path,
            filename=f"flyer-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        )
        if flyer_url:
            ig_post_id = instagram.post_image(
                image_path=None,
                caption=rewritten["instagram_caption"],
                public_image_url=flyer_url,
            )
            logger.info(f"Instagram: {'OK ID=' + str(ig_post_id) if ig_post_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error en flyer/Instagram: {e}")
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

    # 9. WhatsApp
    wa_sent = whatsapp.send_to_channel(
        text=rewritten.get("whatsapp_text", ""),
        wp_post_url=wp_post_url,
    )

    # 10. Registrar en DB
    database.mark_published(
        url=url,
        title=rewritten["title"],
        source=fuente,
        wp_post_id=str(wp_post_id),
        fb_post_id=str(fb_post_id) if fb_post_id else None,
        ig_post_id=str(ig_post_id) if ig_post_id else None,
        wa_sent=wa_sent,
    )

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"✓ PUBLICADO")
    logger.info(f"  WP:  {wp_post_url}")
    logger.info(f"  FB:  {fb_post_id or 'falló'}")
    logger.info(f"  IG:  {ig_post_id or 'falló'}")
    logger.info(f"  WA:  {wa_sent}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def main():
    parser = argparse.ArgumentParser(description="Publica una URL específica en todos los canales.")
    parser.add_argument("url", help="URL del artículo a publicar")
    parser.add_argument("--fuente", default="Nuevo Diario", help="Nombre de la fuente")
    args = parser.parse_args()
    publicar(args.url.strip(), args.fuente.strip())


if __name__ == "__main__":
    main()
