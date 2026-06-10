import requests
import logging
import time
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"
WP_DOMAIN = "ahoranoticias.com.ar"   # dominio propio — NUNCA linkear a otro


def _force_scrape(url: str, token: str) -> str | None:
    """
    Fuerza a Facebook a scrapear el og:image del URL ANTES de publicar.
    Sin esto, Facebook puede publicar el post sin imagen en móvil si el
    scrape asíncrono no terminó a tiempo.
    Retorna la URL de la imagen que Facebook encontró, o None.
    """
    try:
        r = requests.get(
            "https://graph.facebook.com/",
            params={"id": url, "scrape": "true", "access_token": token},
            timeout=20,
        )
        if r.ok:
            data = r.json()
            # Intentar extraer la imagen que Facebook cacheó
            og = data.get("og_object") or {}
            imgs = og.get("image") or data.get("image") or []
            img_url = imgs[0].get("url") if imgs else None
            logger.info(f"Facebook pre-scrape OK | imagen={img_url or 'ninguna'}")
            return img_url
        else:
            logger.warning(f"Facebook pre-scrape warning: {r.text[:150]}")
    except Exception as e:
        logger.warning(f"Facebook pre-scrape error (no fatal): {e}")
    return None


def post_link(
    title: str,
    wp_post_url: str,
    original_url: str,
    image_url: str = None,
) -> str | None:
    """
    Publica en Facebook como LINK POST estándar apuntando a ahoranoticias.com.ar.

    Pasos:
    1. Valida que el URL sea de nuestro dominio.
    2. Fuerza el scrape del og:image en Facebook (para que móvil lo muestre al instante).
    3. Publica el link post con message + link.

    REGLA CRÍTICA: si wp_post_url no es de nuestro sitio, se cancela.
    NUNCA se linkea a la fuente original (Infobae, El Liberal, etc.).
    """
    link = (wp_post_url or "").strip()
    if not link or WP_DOMAIN not in link:
        logger.error(
            f"Facebook BLOQUEADO: '{link}' no pertenece a {WP_DOMAIN}. "
            f"Publicación cancelada para evitar linkear a fuentes externas."
        )
        return None

    page  = config.FB_PAGE_ID
    token = config.META_ACCESS_TOKEN

    # Paso 1: forzar scrape para que Facebook cachee la og:image ANTES de publicar
    _force_scrape(link, token)
    # Pequeña pausa para que el scrape se procese
    time.sleep(3)

    message = f"\U0001f4f0 {title}\n\nLeé la nota completa en nuestro sitio \U0001f447"

    try:
        r = requests.post(
            f"{GRAPH_URL}/{page}/feed",
            data={
                "message": message,
                "link": link,
                "access_token": token,
            },
            timeout=30,
        )
        r.raise_for_status()
        post_id = r.json().get("id")
        logger.info(f"Facebook: link post publicado ID={post_id} | {link}")
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
