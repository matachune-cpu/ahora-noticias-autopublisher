"""
Inyecta manualmente un artículo para ser reescrito y publicado en todos los canales.
Uso: python inject_article.py <url> [--source "Nombre Fuente"] [--title "Título"] [--text "Texto fallback"]
"""
import sys
import os
import logging
import argparse
import tempfile
from datetime import datetime

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("inject_article")

import config
import database
from scraper import extract_article, Article
from rewriter import rewrite_article, check_watermark
from flyer_generator import generate_flyer
from publishers import wordpress, facebook, instagram, whatsapp

IG_RELEVANCE_MIN = 7


def inject(url: str, source_name: str = "Página 12", title: str = "", fallback_text: str = "") -> bool:
    """Procesa y publica un artículo manualmente, omitiendo la deduplicación automática."""

    database.init_db()

    if database.is_published(url):
        logger.warning(f"Este artículo ya fue publicado anteriormente: {url}")
        return False

    # Intentar extraer el artículo desde la URL
    logger.info(f"Extrayendo artículo de: {url}")
    article = extract_article(url, source_name, title or url, fallback_text[:500])

    # Si falla el scraping y se proveyó texto de respaldo, usarlo directamente
    if not article and fallback_text:
        logger.info("Scraping insuficiente — usando texto de respaldo proporcionado.")
        article = Article(
            url=url,
            title=title or url,
            summary=fallback_text[:500],
            full_text=fallback_text,
            source_name=source_name,
            image_url=None,
        )

    if not article:
        logger.error("No se pudo obtener el contenido del artículo. Abortando.")
        return False

    logger.info(f"Artículo obtenido: {article.title[:80]}")
    logger.info(f"Texto ({len(article.full_text)} chars), imagen: {article.image_url or 'ninguna'}")

    # Reescribir con Gemini
    logger.info("Reescribiendo artículo con IA (Gemini)...")
    rewritten = rewrite_article(article.title, article.full_text, source_name)

    if not rewritten.get("es_publicable", False):
        logger.warning(
            f"La IA rechazó el contenido como no publicable: "
            f"{rewritten.get('title') or article.title[:70]}"
        )
        return False

    logger.info(f"Título reescrito: {rewritten['title']}")

    categoria = rewritten.get("categoria", "")
    ig_score = rewritten.get("ig_relevancia", 5)

    # Verificar marca de agua en la imagen
    imagen_limpia = article.image_url
    if imagen_limpia and check_watermark(imagen_limpia):
        logger.info("Imagen descartada por marca de agua detectada.")
        imagen_limpia = None

    # 1. Subir imagen original a WordPress
    media_id = None
    media_url = None
    if imagen_limpia:
        media_id, media_url = wordpress.upload_image(
            image_url=imagen_limpia,
            filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        )

    # 2. Publicar en WordPress
    wp_post_id, wp_post_url = wordpress.create_post(
        title=rewritten["title"],
        body_html=rewritten["body_html"],
        original_url=url,
        source_name=source_name,
        featured_media_id=media_id,
    )
    logger.info(f"WordPress: post_id={wp_post_id} | url={wp_post_url}")

    # 3. Publicar en Facebook
    fb_image = media_url or imagen_limpia
    fb_post_id = facebook.post_link(
        title=rewritten["title"],
        wp_post_url=wp_post_url or url,
        original_url=url,
        image_url=fb_image,
    )
    logger.info(f"Facebook: post_id={fb_post_id}")

    # 4. Generar flyer e incorporar a la cola de Instagram (si relevancia >= 7)
    flyer_public_url = None
    flyer_path = None
    ig_encolado = False

    if ig_score >= IG_RELEVANCE_MIN:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name
        try:
            generate_flyer(
                title=rewritten["title"],
                source_name=source_name,
                article_image_url=imagen_limpia,
                template_path=config.FLYER_TEMPLATE_PATH,
                output_path=flyer_path,
                categoria=categoria,
            )
            _, flyer_public_url = wordpress.upload_image(
                image_path=flyer_path,
                filename=f"flyer-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
            )
            added = database.ig_queue_add(
                url=url,
                title=rewritten["title"],
                ig_caption=rewritten["instagram_caption"],
                flyer_public_url=flyer_public_url,
                relevance_score=ig_score,
            )
            ig_encolado = added
            logger.info(
                f"Instagram: score={ig_score}/10 | "
                f"{'encolado ✓' if added else 'ya en cola'} | "
                f"pendientes={database.ig_queue_count_pending()}"
            )
        except Exception as e:
            logger.error(f"Error generando flyer para Instagram: {e}")
        finally:
            if flyer_path and os.path.exists(flyer_path):
                try:
                    os.unlink(flyer_path)
                except Exception:
                    pass
    else:
        logger.info(f"Instagram omitido: score={ig_score}/10 (mínimo requerido: {IG_RELEVANCE_MIN})")

    # 5. Enviar a WhatsApp
    wa_sent = whatsapp.send_to_channel(
        text=rewritten["whatsapp_text"],
        wp_post_url=wp_post_url,
    )
    logger.info(f"WhatsApp: {'enviado ✓' if wa_sent else 'falló ✗'}")

    # 6. Registrar en la base de datos
    database.mark_published(
        url=url,
        title=rewritten["title"],
        source=source_name,
        wp_post_id=str(wp_post_id) if wp_post_id else None,
        fb_post_id=str(fb_post_id) if fb_post_id else None,
        ig_post_id=None,
        wa_sent=wa_sent,
    )

    logger.info(
        f"\n✅ Artículo publicado exitosamente\n"
        f"   Título:    {rewritten['title']}\n"
        f"   Categoría: {categoria} | Región: {rewritten.get('region')} | IG score: {ig_score}/10\n"
        f"   WordPress: {wp_post_url}\n"
        f"   Facebook:  post_id={fb_post_id}\n"
        f"   Instagram: {'encolado para próxima ventana horaria' if ig_encolado else 'omitido'}\n"
        f"   WhatsApp:  {'enviado' if wa_sent else 'no enviado'}"
    )
    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Inyecta manualmente un artículo para publicar.")
    parser.add_argument("url", nargs="?", help="URL del artículo a publicar")
    parser.add_argument("--source", default="Página 12", help="Nombre de la fuente (default: Página 12)")
    parser.add_argument("--title", default="", help="Título alternativo si el scraping falla")
    parser.add_argument("--text", default="", help="Texto de respaldo si el scraping falla")
    args = parser.parse_args()

    # Si no se pasa URL por argumento, usa el artículo hardcodeado
    article_url = args.url or "https://www.pagina12.com.ar/2026/05/26/no-importara-que-estudien-los-chicos/"
    article_source = args.source
    article_title = args.title or "No importará qué estudien los chicos"
    article_text = args.text or (
        "El CEO de NVIDIA, Jensen Huang, volvió a posicionarse en el centro del debate global "
        "sobre inteligencia artificial, educación y trabajo con una definición que resume parte "
        "de la visión que hoy domina en Silicon Valley: en la era de la IA, lo importante no será "
        "tanto qué carrera estudien las personas, sino cómo aprendan a utilizar la inteligencia "
        "artificial para potenciar sus capacidades.\n\n"
        "Durante una entrevista con Channel NewsAsia, Huang sostuvo que los conocimientos "
        "tradicionales seguirán teniendo valor incluso en un escenario de automatización masiva. "
        "Para el ejecutivo, disciplinas como el periodismo, la narrativa, el diseño y las artes "
        "continuarán siendo relevantes porque la capacidad humana de crear sentido, interpretar "
        "contextos y conectar emocionalmente con una audiencia seguirá siendo diferencial.\n\n"
        "La declaración del CEO de una de las empresas más valiosas del mundo —NVIDIA acumula "
        "una capitalización de mercado superior a los tres billones de dólares gracias al auge "
        "de los chips de inteligencia artificial— llega en un momento en que el debate sobre el "
        "futuro del trabajo y la educación se intensifica en todo el mundo.\n\n"
        "Huang no fue el único ejecutivo tecnológico en plantear este tipo de escenario. "
        "Figuras como Sam Altman, CEO de OpenAI, también han señalado que la IA transformará "
        "radicalmente el mercado laboral, aunque los matices sobre qué habilidades seguirán "
        "siendo irreemplazables varían según el interlocutor.\n\n"
        "Lo que distingue la postura de Huang es su énfasis en que la adaptabilidad y el "
        "aprendizaje continuo serán más valiosos que cualquier título universitario específico. "
        "En su visión, la capacidad de trabajar junto a la IA y aprovechar sus capacidades "
        "será el diferencial clave en el mercado laboral del futuro."
    )

    success = inject(
        url=article_url,
        source_name=article_source,
        title=article_title,
        fallback_text=article_text,
    )
    sys.exit(0 if success else 1)
