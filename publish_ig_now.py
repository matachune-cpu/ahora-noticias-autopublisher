"""
Publica inmediatamente los artículos pendientes en la cola de Instagram,
ignorando las ventanas horarias configuradas.
Uso: python publish_ig_now.py [--limit N]
"""
import sys
import time
import logging
import argparse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("publish_ig_now")

import database
from publishers import instagram

IG_DAILY_LIMIT = 50


def publish_now(limit: int = 5):
    database.init_db()

    posts_hoy = database.ig_queue_count_today()
    restantes = IG_DAILY_LIMIT - posts_hoy
    if restantes <= 0:
        logger.warning(f"Límite diario de Instagram alcanzado ({posts_hoy}/{IG_DAILY_LIMIT}). No se puede publicar.")
        return

    a_publicar = min(limit, restantes)
    pendientes = database.ig_queue_get_pending(limit=a_publicar)

    if not pendientes:
        logger.info("No hay artículos pendientes en la cola de Instagram.")
        return

    logger.info(f"Publicando {len(pendientes)} artículo(s) en Instagram (forzado, sin ventana horaria)...")

    publicados = 0
    for item in pendientes:
        logger.info(f"  → {item['title'][:70]} (score={item['relevance_score']})")
        ig_post_id = instagram.post_image(
            image_path=None,
            caption=item["ig_caption"],
            public_image_url=item["flyer_public_url"],
        )
        if ig_post_id:
            database.ig_queue_mark_posted(item["original_url"], ig_post_id)
            logger.info(f"  ✓ Publicado en Instagram: ID={ig_post_id}")
            publicados += 1
        else:
            logger.warning(f"  ✗ Falló la publicación en Instagram: {item['title'][:60]}")
        time.sleep(4)

    logger.info(f"\n✅ {publicados}/{len(pendientes)} artículos publicados en Instagram.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Publica la cola de Instagram ahora mismo.")
    parser.add_argument("--limit", type=int, default=5, help="Máximo de posts a publicar (default: 5)")
    args = parser.parse_args()
    publish_now(limit=args.limit)
