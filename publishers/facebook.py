import requests
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"


def post_link(title: str, wp_post_url: str, original_url: str) -> str | None:
    """
    Publica en la página de Facebook con el enlace al post de WordPress.
    Retorna el post ID o None.
    """
    try:
        message = f"📰 {title}\n\nLeé la nota completa en nuestro sitio 👇"
        payload = {
            "message": message,
            "link": wp_post_url or original_url,
            "access_token": config.META_ACCESS_TOKEN,
        }
        resp = requests.post(
            f"{GRAPH_URL}/{config.FB_PAGE_ID}/feed",
            data=payload,
            timeout=20,
        )
        resp.raise_for_status()
        post_id = resp.json().get("id")
        logger.info(f"Facebook: publicado ID={post_id}")
        return post_id
    except Exception as e:
        logger.error(f"Facebook post_link error: {e}")
        return None
