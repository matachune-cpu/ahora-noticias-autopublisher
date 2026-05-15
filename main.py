"""
News Auto-Publisher
Monitorea RSS de diarios, reescribe con IA y publica en WordPress, Facebook, Instagram y WhatsApp.
"""
import os
import time
import logging
import schedule
import tempfile
from datetime import datetime

import config
import database
from scraper import fetch_entries, extract_article
from rewriter import rewrite_article, check_watermark
from flyer_generator import generate_flyer
from publishers import wordpress, facebook, instagram, whatsapp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("autopublisher.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


REGION_PRIORITY = {"Argentina": 0, "Latinoamerica": 1, "Internacional": 2}


def _region_sort_key(item):
    return REGION_PRIORITY.get(item.get("region", "Argentina"), 2)


def process_source(source: dict):
    logger.info(f"Procesando fuente: {source['name']}")
    entries = fetch_entries(source, max_items=source.get("max_articles", config.MAX_ARTICLES_PER_RUN))
    processed = 0

    # Pre-procesar: extraer + reescribir para ordenar por prioridad geográfica
    pending = []
    for entry in entries:
        url = entry["url"]
        if not url:
            continue
        if database.is_published(url):
            logger.debug(f"Ya publicado: {url}")
            continue

        logger.info(f"Nueva noticia: {entry['title'][:80]}")

        # 1. Extraer artículo completo
        article = extract_article(url, source["name"], entry["title"], entry["summary"])
        if not article:
            logger.warning(f"No se pudo extraer: {url}")
            continue

        # 2. Reescribir con Claude (incluye categoría y región)
        rewritten = rewrite_article(article.title, article.full_text, source["name"])
        pending.append({"url": url, "article": article, "rewritten": rewritten, "region": rewritten.get("region", "Argentina")})

    # Ordenar: Argentina primero, Latinoamérica segundo, Internacional último
    pending.sort(key=_region_sort_key)
    if pending:
        logger.info(f"  → Orden por región: {[p['region'] for p in pending]}")

    for item in pending:
        url = item["url"]
        article = item["article"]
        rewritten = item["rewritten"]
        categoria = rewritten.get("categoria", "")

        # 3. Verificar marca de agua en la imagen
        imagen_limpia = article.image_url
        if imagen_limpia and check_watermark(imagen_limpia):
            logger.info(f"Imagen descartada por marca de agua: {imagen_limpia}")
            imagen_limpia = None  # no usar imagen con watermark

        # 4. Subir foto ORIGINAL a WordPress como imagen destacada
        wp_post_id = None
        wp_post_url = None
        media_id = None
        wp_photo_url = None

        if imagen_limpia:
            media_id, wp_photo_url = wordpress.upload_image(
                image_url=imagen_limpia,
                filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
            )

        # 4. Publicar en WordPress con la foto original como imagen destacada
        wp_post_id, wp_post_url = wordpress.create_post(
            title=rewritten["title"],
            body_html=rewritten["body_html"],
            original_url=url,
            source_name=source["name"],
            featured_media_id=media_id,
        )

        # 5. Publicar en Facebook (usa el link de WP, que ya tiene la foto original)
        fb_post_id = facebook.post_link(
            title=rewritten["title"],
            wp_post_url=wp_post_url or url,
            original_url=url,
        )

        # 6. Generar flyer diseñado SOLO para Instagram
        flyer_path = None
        flyer_public_url = None
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name

        try:
            generate_flyer(
                title=rewritten["title"],
                source_name=source["name"],
                article_image_url=imagen_limpia,
                template_path=config.FLYER_TEMPLATE_PATH,
                output_path=flyer_path,
                categoria=categoria,
            )
            # Subir flyer a WP solo para obtener URL pública (sin asignarlo al post)
            _, flyer_public_url = wordpress.upload_image(
                image_path=flyer_path,
                filename=f"flyer-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
            )
        except Exception as e:
            logger.error(f"Error generando flyer: {e}")
            flyer_path = None

        # 7. Publicar en Instagram con el flyer
        ig_post_id = None
        if flyer_path and os.path.exists(flyer_path):
            ig_post_id = instagram.post_image(
                image_path=flyer_path,
                caption=rewritten["instagram_caption"],
                public_image_url=flyer_public_url,
            )

        # 7. Publicar en WhatsApp
        wa_sent = whatsapp.send_to_channel(
            text=rewritten["whatsapp_text"],
            wp_post_url=wp_post_url,
        )

        # 8. Registrar en base de datos
        database.mark_published(
            url=url,
            title=rewritten["title"],
            source=source["name"],
            wp_post_id=str(wp_post_id) if wp_post_id else None,
            fb_post_id=str(fb_post_id) if fb_post_id else None,
            ig_post_id=str(ig_post_id) if ig_post_id else None,
            wa_sent=wa_sent,
        )

        # Limpiar flyer temporal
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

        logger.info(
            f"✓ Publicado: WP={wp_post_id} | FB={fb_post_id} | IG={ig_post_id} | WA={wa_sent}"
        )
        processed += 1

        # Pausa entre artículos para no saturar APIs
        time.sleep(5)

    logger.info(f"  → {source['name']}: {processed} artículos nuevos publicados")


def run_cycle():
    logger.info("=" * 60)
    logger.info(f"Iniciando ciclo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    for source in config.NEWS_SOURCES:
        try:
            process_source(source)
        except Exception as e:
            logger.error(f"Error procesando {source['name']}: {e}")
        time.sleep(3)
    logger.info("Ciclo finalizado.")


def main():
    logger.info("News Auto-Publisher iniciado.")
    database.init_db()

    # Primera corrida inmediata
    run_cycle()

    # Programar corridas periódicas
    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_cycle)
    logger.info(f"Corriendo cada {config.CHECK_INTERVAL_MINUTES} minutos...")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
