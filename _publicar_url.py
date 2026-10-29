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


def publicar(
    url: str,
    fuente: str,
    sticky: bool = False,
    categories: list = None,
    platforms: str = "all",
    force: bool = False,
    instrucciones: str = "",
):
    """
    platforms: 'all' | 'wp_only' | 'wp_fb' | 'wp_ig_fb' | 'no_ig'
    force: si True, publica aunque la URL ya esté en la DB.
    instrucciones: instrucciones editoriales adicionales para Gemini.
    """
    database.init_db()

    do_fb = platforms not in ("wp_only",)
    do_ig = platforms in ("all", "wp_ig_fb")
    do_wa = platforms not in ("wp_only",)

    logger.info(f"━━━━ Publicando: {url}")
    logger.info(f"      Fuente: {fuente} | sticky={sticky} | plataformas={platforms}")

    # 1. Verificar si ya fue publicada
    if not force and database.is_published(url):
        logger.warning("Esta URL ya fue publicada anteriormente. Abortando.")
        sys.exit(0)

    # 2. Extraer artículo
    article = extract_article(url, source_name=fuente, title="", summary="")
    if not article:
        logger.error("No se pudo extraer contenido del artículo. Abortando.")
        sys.exit(1)
    logger.info(f"Título extraído: {article.title[:80]}")

    # 3. Reescribir con Gemini
    rewritten = rewrite_article(article.title, article.full_text, fuente, extra_instructions=instrucciones)
    if not rewritten.get("es_publicable"):
        logger.error("Gemini rechazó el contenido. Abortando.")
        sys.exit(1)
    logger.info(f"Título reescrito: {rewritten['title'][:80]}")

    # 4. Resolver imagen con validación completa (técnica + semántica + visual Gemini)
    from image_resolver import resolve_news_image
    img_result = resolve_news_image(
        title=rewritten["title"],
        summary=rewritten.get("whatsapp_text", ""),
        article_url=url,
        article_image_url=article.image_url,
    )

    if img_result["status"] != "VALIDATED":
        logger.warning(
            f"Sin imagen validada — publicación social cancelada. "
            f"Razones: {img_result.get('rejection_reasons', [])}"
        )
        imagen = None
        imagen_validada = False
    else:
        imagen = img_result["image_url"]
        imagen_validada = True
        logger.info(
            f"Imagen validada | estrategia={img_result['strategy']} "
            f"| score={img_result['final_score']:.0f} | {imagen[:80]}"
        )

    # 5. Subir imagen a WordPress si hay
    media_id = None
    media_url = None
    if imagen:
        media_id, media_url = wordpress.upload_image(
            image_url=imagen,
            filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        )

    # Resolver IDs de categorías si se especificaron
    cat_ids = []
    if categories:
        for cat_name in categories:
            cat_id = wordpress.get_or_create_category(cat_name.strip())
            if cat_id:
                cat_ids.append(cat_id)

    # 6. Publicar en WordPress
    wp_post_id, wp_post_url = wordpress.create_post(
        title=rewritten["title"],
        body_html=rewritten["body_html"],
        original_url=url,
        source_name=fuente,
        featured_media_id=media_id,
        sticky=sticky,
        categories=cat_ids or None,
    )
    if not wp_post_id:
        logger.error("WordPress falló. Abortando publicación en redes.")
        database.mark_seen(url, rewritten["title"], fuente)
        sys.exit(1)
    logger.info(f"WordPress: post creado → {wp_post_url}")

    # 7. WhatsApp — puede publicar sin imagen (solo texto + link)
    wa_sent = False
    if do_wa:
        wa_sent = whatsapp.send_to_channel(
            text=rewritten.get("whatsapp_text", ""),
            wp_post_url=wp_post_url,
        )

    # GUARD CLAUSE: no publicar en redes sociales sin imagen validada
    if not imagen_validada:
        logger.warning(
            "SOCIAL_PUBLICATION_BLOCKED: imagen no validada. "
            "Noticia publicada en WordPress y WhatsApp únicamente."
        )
        database.mark_published(
            url=url,
            title=rewritten["title"],
            source=fuente,
            wp_post_id=str(wp_post_id),
            fb_post_id=None,
            ig_post_id=None,
            wa_sent=wa_sent,
        )
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info("PUBLICADO (solo web, sin redes por falta de imagen validada)")
        logger.info(f"  WP:  {wp_post_url}")
        logger.info(f"  WA:  {wa_sent}")
        logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        return

    # 8. Generar flyer ANTES de publicar en redes (imagen ya validada — no puede ser None)
    ig_post_id = None
    flyer_path = None
    flyer_url = None
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
        logger.info(f"Flyer generado: {flyer_url[:80] if flyer_url else 'falló'}")
    except Exception as e:
        logger.error(f"Error generando flyer: {e}")
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

    # 9. Publicar en Facebook — imagen de artículo > flyer
    fb_post_id = None
    if do_fb:
        fb_image = media_url or flyer_url
        fb_post_id = facebook.post_link(
            title=rewritten["title"],
            wp_post_url=wp_post_url,
            original_url=url,
            image_url=fb_image,
            caption=rewritten.get("facebook_caption"),
        )
        logger.info(f"Facebook: {'OK ID=' + str(fb_post_id) if fb_post_id else 'FALLÓ'} | imagen={'sí' if fb_image else 'no'}")

    # 10. Publicar en Instagram con el mismo flyer
    if do_ig and flyer_url:
        try:
            ig_post_id = instagram.post_image(
                image_path=None,
                caption=rewritten["instagram_caption"],
                public_image_url=flyer_url,
            )
            logger.info(f"Instagram: {'OK ID=' + str(ig_post_id) if ig_post_id else 'FALLÓ'}")
        except Exception as e:
            logger.error(f"Error en Instagram: {e}")

    # 11. Registrar en DB
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
    logger.info(f"PUBLICADO")
    logger.info(f"  WP:  {wp_post_url}")
    logger.info(f"  FB:  {fb_post_id or 'falló'}")
    logger.info(f"  IG:  {ig_post_id or 'falló'}")
    logger.info(f"  WA:  {wa_sent}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")


def main():
    parser = argparse.ArgumentParser(description="Publica una URL específica en todos los canales.")
    parser.add_argument("url", help="URL del artículo a publicar")
    parser.add_argument("--fuente", default="Nuevo Diario", help="Nombre de la fuente")
    parser.add_argument("--sticky", action="store_true", help="Fijar en portada de WordPress")
    parser.add_argument("--categories", default="", help="Categorías separadas por coma (ej: Política,Nacionales)")
    parser.add_argument(
        "--platforms",
        default="all",
        choices=["all", "wp_only", "wp_fb", "wp_ig_fb", "no_ig"],
        help="Plataformas donde publicar",
    )
    parser.add_argument("--force", action="store_true", help="Publicar aunque la URL ya esté en la DB")
    parser.add_argument("--instrucciones", default="", help="Instrucciones editoriales adicionales para Gemini")
    args = parser.parse_args()

    cats = [c.strip() for c in args.categories.split(",") if c.strip()] if args.categories else []

    publicar(
        url=args.url.strip(),
        fuente=args.fuente.strip(),
        sticky=args.sticky,
        categories=cats,
        platforms=args.platforms,
        force=args.force,
        instrucciones=args.instrucciones,
    )


if __name__ == "__main__":
    main()
