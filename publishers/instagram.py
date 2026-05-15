"""
Publica en Instagram Business usando Meta Graph API (Content Publishing).
Límite diario: 15 posts para no superar el máximo de la API (50/día).
"""
import requests
import logging
import sqlite3
from datetime import date
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"
IG_DAILY_LIMIT = 15
DB_PATH = "published_articles.db"


def _get_ig_posts_today() -> int:
    """Cuenta cuántos posts se publicaron en Instagram hoy."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            today = date.today().isoformat()
            row = conn.execute(
                "SELECT COUNT(*) FROM articles WHERE ig_post_id IS NOT NULL AND created_at LIKE ?",
                (f"{today}%",)
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def post_image(image_path: str, caption: str, public_image_url: str = None) -> str | None:
    """
    Publica el flyer en Instagram.
    Respeta el límite diario de 15 posts.
    Retorna el post ID o None.
    """
    try:
        # Verificar límite diario
        posts_today = _get_ig_posts_today()
        if posts_today >= IG_DAILY_LIMIT:
            logger.warning(f"Instagram: limite diario alcanzado ({posts_today}/{IG_DAILY_LIMIT}). Saltando.")
            return None

        if not public_image_url:
            logger.error("Instagram: no hay URL publica de imagen disponible.")
            return None

        # Paso 1: crear container
        container_resp = requests.post(
            f"{GRAPH_URL}/{config.IG_ACCOUNT_ID}/media",
            data={
                "image_url": public_image_url,
                "caption": caption,
                "access_token": config.META_ACCESS_TOKEN,
            },
            timeout=30,
        )
        container_resp.raise_for_status()
        container_id = container_resp.json().get("id")

        if not container_id:
            logger.error("Instagram: no se obtuvo container_id")
            return None

        # Paso 2: verificar que el container esté listo
        import time
        time.sleep(3)
        status_resp = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code", "access_token": config.META_ACCESS_TOKEN},
            timeout=15,
        )
        status = status_resp.json().get("status_code", "")
        if status == "ERROR":
            logger.error(f"Instagram: container con error, abortando")
            return None

        # Paso 3: publicar
        publish_resp = requests.post(
            f"{GRAPH_URL}/{config.IG_ACCOUNT_ID}/media_publish",
            data={
                "creation_id": container_id,
                "access_token": config.META_ACCESS_TOKEN,
            },
            timeout=30,
        )
        publish_resp.raise_for_status()
        post_id = publish_resp.json().get("id")
        logger.info(f"Instagram: publicado ID={post_id} ({posts_today + 1}/{IG_DAILY_LIMIT} hoy)")
        return post_id
    except Exception as e:
        logger.error(f"Instagram post_image error: {e}")
        return None
