import json
import requests
import base64
import logging
import config

logger = logging.getLogger(__name__)


def _auth_header() -> dict:
    credentials = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def upload_image(image_path: str = None, filename: str = "foto.jpg", image_url: str = None) -> tuple:
    """
    Sube una imagen a la Media Library de WordPress.
    Acepta un archivo local (image_path) o una URL remota (image_url).
    Retorna (media_id, media_url).
    """
    try:
        api_url = f"{config.WP_URL}/wp-json/wp/v2/media"

        if image_url and not image_path:
            # Descargar la imagen desde la URL y subirla
            r = requests.get(image_url, timeout=15)
            r.raise_for_status()
            img_data = r.content
            # Detectar extensión
            ct = r.headers.get("Content-Type", "image/jpeg")
            ext = "jpg" if "jpeg" in ct or "jpg" in ct else ct.split("/")[-1]
            filename = f"foto.{ext}"
        else:
            with open(image_path, "rb") as f:
                img_data = f.read()

        headers = {
            **_auth_header(),
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Type": "image/jpeg",
        }
        resp = requests.post(api_url, headers=headers, data=img_data, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        media_id = data.get("id")
        media_url = data.get("source_url", "")
        logger.info(f"WordPress: imagen subida, media ID={media_id}")
        return media_id, media_url
    except Exception as e:
        logger.error(f"WordPress upload_image error: {e}")
        return None, None


def create_post(
    title: str,
    body_html: str,
    original_url: str,
    source_name: str,
    featured_media_id: int = None,
) -> str | None:
    """
    Crea un post en WordPress.
    Retorna el post ID como string o None si falla.
    """
    try:
        attribution = (
            f'<p><em>Fuente original: <a href="{original_url}" target="_blank" rel="noopener">'
            f"{source_name}</a></em></p>"
        )
        full_content = body_html + attribution

        payload = {
            "title": title,
            "content": full_content,
            "status": "publish",
        }
        if featured_media_id:
            payload["featured_media"] = featured_media_id

        url = f"{config.WP_URL}/wp-json/wp/v2/posts"
        headers = {
            **_auth_header(),
            "Content-Type": "application/json",
        }
        resp = requests.post(url, data=json.dumps(payload), headers=headers, timeout=30)
        resp.raise_for_status()
        post_data = resp.json()
        post_id = str(post_data["id"])
        post_url = post_data.get("link", "")
        logger.info(f"WordPress: post creado ID={post_id} URL={post_url}")
        return post_id, post_url
    except Exception as e:
        logger.error(f"WordPress create_post error: {e}")
        return None, None
