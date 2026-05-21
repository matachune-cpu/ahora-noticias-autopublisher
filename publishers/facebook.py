import requests
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"


def post_link(
    title: str,
    wp_post_url: str,
    original_url: str,
    image_url: str = None,
) -> str | None:
    """
    Publica en la página de Facebook.

    Si se provee image_url, publica como post de FOTO con el link en el caption.
    De esta forma la imagen se muestra siempre correctamente sin depender
    de que Facebook scrapee el og:image de WordPress.

    Si no hay imagen disponible, hace un post de link estándar (fallback).
    Retorna el post ID o None.
    """
    try:
        link = wp_post_url or original_url
        message = f"📰 {title}\n\nLee la nota completa en nuestro sitio 👇\n{link}"

        if image_url:
            # ── Foto directa: la imagen siempre se muestra como se espera ──────
            payload = {
                "url": image_url,          # Facebook descarga la imagen desde esta URL
                "caption": message,
                "access_token": config.META_ACCESS_TOKEN,
            }
            resp = requests.post(
                f"{GRAPH_URL}/{config.FB_PAGE_ID}/photos",
                data=payload,
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            # /photos retorna {"id": photo_id, "post_id": feed_post_id}
            post_id = data.get("post_id") or data.get("id")
            logger.info(f"Facebook: foto publicada ID={post_id}")
        else:
            # ── Fallback link post (sin imagen) ──────────────────────────────
            payload = {
                "message": message,
                "link": link,
                "access_token": config.META_ACCESS_TOKEN,
            }
            resp = requests.post(
                f"{GRAPH_URL}/{config.FB_PAGE_ID}/feed",
                data=payload,
                timeout=20,
            )
            resp.raise_for_status()
            post_id = resp.json().get("id")
            logger.info(f"Facebook: link publicado ID={post_id}")

        return post_id
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Facebook HTTP error: {e} | "
            f"response={e.response.text[:300] if e.response is not None else 'N/A'}"
        )
        return None
    except Exception as e:
        logger.error(f"Facebook post_link error: {e}")
        return None
