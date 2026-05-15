"""
Publica en Instagram Business usando Meta Graph API (Content Publishing).
Requiere que la imagen esté en una URL pública accesible (se usa imgbb como hosting temporal).
"""
import requests
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"
IMGBB_API_KEY = None  # Opcional: configurar si se usa imgbb


def _upload_to_imgbb(image_path: str) -> str | None:
    """Sube la imagen a imgbb y retorna la URL pública."""
    if not IMGBB_API_KEY:
        return None
    try:
        import base64
        with open(image_path, "rb") as f:
            b64 = base64.b64encode(f.read()).decode()
        resp = requests.post(
            "https://api.imgbb.com/1/upload",
            data={"key": IMGBB_API_KEY, "image": b64},
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()["data"]["url"]
    except Exception as e:
        logger.error(f"imgbb upload error: {e}")
        return None


def post_image(image_path: str, caption: str, public_image_url: str = None) -> str | None:
    """
    Publica el flyer en Instagram.
    public_image_url: URL pública de la imagen (requerido por Meta Graph API).
    Retorna el post ID o None.
    """
    try:
        # Si no hay URL pública, intentar con imgbb
        if not public_image_url:
            public_image_url = _upload_to_imgbb(image_path)

        if not public_image_url:
            logger.error("Instagram: no hay URL pública de imagen disponible.")
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

        # Paso 2: publicar el container
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
    except Exception as e:
        logger.error(f"Instagram post_image error: {e}")
        return None
