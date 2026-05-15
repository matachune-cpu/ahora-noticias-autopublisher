"""
Publica en Instagram Business usando Meta Graph API (Content Publishing).
El control de límite diario y ventanas horarias se maneja en main.py a través de la cola.
"""
import requests
import logging
import time
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"


def post_image(image_path: str, caption: str, public_image_url: str = None) -> str | None:
    """
    Publica una imagen en Instagram.
    public_image_url: URL pública accesible por Meta (requerido).
    image_path: no se usa directamente (la imagen ya está en WP como URL pública).
    Retorna el post ID o None si falla.
    """
    try:
        if not public_image_url:
            logger.error("Instagram: no hay URL pública de imagen disponible.")
            return None

        # Paso 1: crear container de media
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
            logger.error(f"Instagram: no se obtuvo container_id. Respuesta: {container_resp.text[:200]}")
            return None

        # Paso 2: esperar y verificar que el container esté listo
        time.sleep(4)
        status_resp = requests.get(
            f"{GRAPH_URL}/{container_id}",
            params={"fields": "status_code,status", "access_token": config.META_ACCESS_TOKEN},
            timeout=15,
        )
        status_data = status_resp.json()
        status_code = status_data.get("status_code", "")

        if status_code == "ERROR":
            logger.error(f"Instagram: container con error: {status_data}")
            return None
        if status_code not in ("FINISHED", "PUBLISHED", ""):
            # Esperar un poco más si todavía está procesando
            logger.info(f"Instagram: container en estado '{status_code}', esperando...")
            time.sleep(5)

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
        logger.info(f"Instagram: publicado ID={post_id}")
        return post_id

    except requests.HTTPError as e:
        body = e.response.text if e.response else ""
        logger.error(f"Instagram HTTP error: {e} | {body[:300]}")
        return None
    except Exception as e:
        logger.error(f"Instagram post_image error: {e}")
        return None
