import json
import requests
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"
WP_DOMAIN = "ahoranoticias.com.ar"   # dominio propio — NUNCA linkear a otro


def post_link(
    title: str,
    wp_post_url: str,
    original_url: str,
    image_url: str = None,
) -> str | None:
    """
    Publica en Facebook siempre linkeando a ahoranoticias.com.ar.

    REGLA CRÍTICA: si wp_post_url no es una URL válida de nuestro sitio,
    NO se publica en Facebook. Nunca se linkea a la fuente original.

    Si hay imagen:
      1) Sube foto como no-publicada → photo_id
      2) Crea post en feed con foto adjunta → aparece en timeline con imagen real

    Si no hay imagen: post de texto + link a nuestro artículo.
    """
    # ── Validar que el link sea SIEMPRE de nuestro sitio ─────────────────────
    link = (wp_post_url or "").strip()
    if not link or WP_DOMAIN not in link:
        logger.error(
            f"Facebook BLOQUEADO: la URL '{link}' no pertenece a {WP_DOMAIN}. "
            f"NUNCA se linkea a fuentes externas. Se cancela la publicación en FB."
        )
        return None

    message = f"📰 {title}\n\nLeé la nota completa en nuestro sitio 👇\n{link}"
    page  = config.FB_PAGE_ID
    token = config.META_ACCESS_TOKEN

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
            # ── Post de texto + link a nuestro sitio ─────────────────────────
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
