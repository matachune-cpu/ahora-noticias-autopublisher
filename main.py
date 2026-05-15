"""
News Auto-Publisher
Monitorea RSS de diarios, reescribe con IA y publica en WordPress, Facebook, Instagram y WhatsApp.
Instagram: cola con scoring de relevancia, publicación en ventanas horarias (6-9h, 12-15h, 21-00h).
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


# ── Prioridad geográfica ──────────────────────────────────────────────────────
REGION_PRIORITY = {"Argentina": 0, "Latinoamerica": 1, "Internacional": 2}


def _region_sort_key(item):
    return REGION_PRIORITY.get(item.get("region", "Argentina"), 2)


# ── Ventanas horarias de Instagram ────────────────────────────────────────────
IG_POSTING_WINDOWS = [
    (6, 9),    # 6:00 – 9:00
    (12, 15),  # 12:00 – 15:00
    (21, 24),  # 21:00 – 00:00
]
IG_MAX_PER_RUN = 2      # máximo posts por ciclo de 30 min dentro de una ventana
IG_DAILY_LIMIT = 50     # límite real de la API de Meta
IG_RELEVANCE_MIN = 7    # puntaje mínimo para entrar a la cola


def _is_ig_window() -> bool:
    """Devuelve True si el horario actual cae en una ventana de publicación IG."""
    hora = datetime.now().hour
    return any(start <= hora < end for start, end in IG_POSTING_WINDOWS)


# ── Procesamiento de fuentes ──────────────────────────────────────────────────

def process_source(source: dict):
    logger.info(f"Procesando fuente: {source['name']}")
    entries = fetch_entries(source, max_items=source.get("max_articles", config.MAX_ARTICLES_PER_RUN))

    # Pre-procesar: extraer + reescribir para poder ordenar por región
    pending = []
    for entry in entries:
        url = entry["url"]
        if not url:
            continue
        if database.is_published(url):
            logger.debug(f"Ya publicado: {url}")
            continue

        logger.info(f"Nueva noticia: {entry['title'][:80]}")

        article = extract_article(url, source["name"], entry["title"], entry["summary"])
        if not article:
            logger.warning(f"No se pudo extraer: {url}")
            continue

        rewritten = rewrite_article(article.title, article.full_text, source["name"])
        pending.append({
            "url": url,
            "article": article,
            "rewritten": rewritten,
            "region": rewritten.get("region", "Argentina"),
        })

    # Ordenar por región: Argentina > Latinoamérica > Internacional
    pending.sort(key=_region_sort_key)
    if pending:
        logger.info(f"  → Orden: {[p['region'] for p in pending]}")

    processed = 0
    for item in pending:
        url = item["url"]
        article = item["article"]
        rewritten = item["rewritten"]
        categoria = rewritten.get("categoria", "")
        ig_score = rewritten.get("ig_relevancia", 5)

        # 1. Verificar marca de agua
        imagen_limpia = article.image_url
        if imagen_limpia and check_watermark(imagen_limpia):
            logger.info(f"Imagen descartada por marca de agua: {imagen_limpia}")
            imagen_limpia = None

        # 2. Subir foto original a WordPress como imagen destacada
        wp_post_id = None
        wp_post_url = None
        media_id = None

        if imagen_limpia:
            media_id, _ = wordpress.upload_image(
                image_url=imagen_limpia,
                filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
            )

        # 3. Publicar en WordPress
        wp_post_id, wp_post_url = wordpress.create_post(
            title=rewritten["title"],
            body_html=rewritten["body_html"],
            original_url=url,
            source_name=source["name"],
            featured_media_id=media_id,
        )

        # 4. Publicar en Facebook
        fb_post_id = facebook.post_link(
            title=rewritten["title"],
            wp_post_url=wp_post_url or url,
            original_url=url,
        )

        # 5. Generar flyer y encolar en Instagram si la nota es lo suficientemente relevante
        flyer_public_url = None
        flyer_path = None
        ig_encolado = False

        if ig_score >= IG_RELEVANCE_MIN:
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
                # Subir flyer a WP para tener URL pública persistente
                _, flyer_public_url = wordpress.upload_image(
                    image_path=flyer_path,
                    filename=f"flyer-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
                )
                # Agregar a la cola de Instagram
                added = database.ig_queue_add(
                    url=url,
                    title=rewritten["title"],
                    ig_caption=rewritten["instagram_caption"],
                    flyer_public_url=flyer_public_url,
                    relevance_score=ig_score,
                )
                ig_encolado = added
                logger.info(
                    f"  → IG cola: score={ig_score}/10 | "
                    f"{'encolado ✓' if added else 'ya en cola'} | "
                    f"pendientes={database.ig_queue_count_pending()}"
                )
            except Exception as e:
                logger.error(f"Error generando flyer para IG: {e}")
            finally:
                if flyer_path and os.path.exists(flyer_path):
                    try:
                        os.unlink(flyer_path)
                    except Exception:
                        pass
        else:
            logger.info(f"  → IG omitido: score={ig_score}/10 (mínimo {IG_RELEVANCE_MIN})")

        # 6. WhatsApp
        wa_sent = whatsapp.send_to_channel(
            text=rewritten["whatsapp_text"],
            wp_post_url=wp_post_url,
        )

        # 7. Registrar en DB (ig_post_id se completará después cuando se publique)
        database.mark_published(
            url=url,
            title=rewritten["title"],
            source=source["name"],
            wp_post_id=str(wp_post_id) if wp_post_id else None,
            fb_post_id=str(fb_post_id) if fb_post_id else None,
            ig_post_id=None,  # se asignará al publicar desde la cola
            wa_sent=wa_sent,
        )

        logger.info(
            f"✓ Publicado: WP={wp_post_id} | FB={fb_post_id} | "
            f"IG={'en cola' if ig_encolado else 'omitido'} | WA={wa_sent}"
        )
        processed += 1
        time.sleep(5)

    logger.info(f"  → {source['name']}: {processed} artículos nuevos publicados")


# ── Publicación desde cola de Instagram ──────────────────────────────────────

def publish_ig_queue():
    """
    Si estamos en una ventana horaria de IG, publica los artículos más relevantes
    de la cola. Máximo IG_MAX_PER_RUN por ciclo. Respeta el límite diario.
    """
    if not _is_ig_window():
        logger.debug("Fuera de ventana horaria de Instagram. Cola en espera.")
        return

    posts_hoy = database.ig_queue_count_today()
    restantes_dia = IG_DAILY_LIMIT - posts_hoy
    if restantes_dia <= 0:
        logger.warning(f"Instagram: límite diario alcanzado ({posts_hoy}/{IG_DAILY_LIMIT}).")
        return

    a_publicar = min(IG_MAX_PER_RUN, restantes_dia)
    pendientes = database.ig_queue_get_pending(limit=a_publicar)

    if not pendientes:
        logger.info("Cola de Instagram vacía en esta ventana.")
        return

    hora_actual = datetime.now().strftime("%H:%M")
    logger.info(
        f"Ventana IG activa ({hora_actual}) | "
        f"hoy={posts_hoy}/{IG_DAILY_LIMIT} | "
        f"publicando {len(pendientes)} de {database.ig_queue_count_pending()} pendientes"
    )

    for item in pendientes:
        ig_post_id = instagram.post_image(
            image_path=None,
            caption=item["ig_caption"],
            public_image_url=item["flyer_public_url"],
        )
        if ig_post_id:
            database.ig_queue_mark_posted(item["original_url"], ig_post_id)
            logger.info(
                f"  ✓ IG publicado: {item['title'][:60]} "
                f"(score={item['relevance_score']}) ID={ig_post_id}"
            )
        else:
            logger.warning(f"  ✗ IG falló: {item['title'][:60]}")
        time.sleep(4)


# ── Ciclo principal ───────────────────────────────────────────────────────────

def run_cycle():
    logger.info("=" * 60)
    logger.info(f"Iniciando ciclo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # 1. Procesar todas las fuentes (WP + FB + encolar IG si relevante)
    for source in config.NEWS_SOURCES:
        try:
            process_source(source)
        except Exception as e:
            logger.error(f"Error procesando {source['name']}: {e}")
        time.sleep(3)

    # 2. Publicar desde cola de Instagram si es horario activo
    publish_ig_queue()

    logger.info("Ciclo finalizado.")


def main():
    logger.info("News Auto-Publisher iniciado.")
    database.init_db()

    run_cycle()

    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_cycle)
    logger.info(f"Corriendo cada {config.CHECK_INTERVAL_MINUTES} minutos...")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
