import json
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

    Si hay imagen disponible:
      1) Sube la foto como no-publicada  →  obtiene photo_id
      2) Crea post en el FEED adjuntando esa foto  →  aparece en el timeline
         con la imagen real, sin depender del scraping de og:image de WordPress.

    Si no hay imagen: hace un post de texto + link al artículo (fallback).

    Retorna el post ID del feed o None si falla.
    """
    link    = wp_post_url or original_url
    message = f"📰 {title}\n\nLeé la nota completa en nuestro sitio 👇\n{link}"
    page    = config.FB_PAGE_ID
    token   = config.META_ACCESS_TOKEN

    try:
        if image_url:
            # ── Paso 1: subir foto sin publicar ──────────────────────────────
            r1 = requests.post(
                f"{GRAPH_URL}/{page}/photos",
                data={"url": image_url, "published": "false", "access_token": token},
                timeout=30,
            )
            r1.raise_for_status()
            photo_id = r1.json().get("id")

            if not photo_id:
                raise ValueError("No se obtuvo photo_id al subir la imagen")

            # ── Paso 2: crear post en el feed con la foto adjunta ─────────────
            r2 = requests.post(
                f"{GRAPH_URL}/{page}/feed",
                data={
                    "message": message,
                    "attached_media[0]": json.dumps({"media_fbid": photo_id}),
                    "access_token": token,
                },
                timeout=30,
            )
            r2.raise_for_status()
            post_id = r2.json().get("id")
            logger.info(f"Facebook: post con imagen publicado ID={post_id}")
            return post_id

        else:
            # ── Fallback: post de texto + link (sin imagen) ───────────────────
            r = requests.post(
                f"{GRAPH_URL}/{page}/feed",
                data={"message": message, "link": link, "access_token": token},
                timeout=20,
            )
            r.raise_for_status()
            post_id = r.json().get("id")
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
