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


def get_or_create_category(name: str) -> int | None:
    """Retorna el ID de la categoría WP (la crea si no existe)."""
    try:
        url = f"{config.WP_URL}/wp-json/wp/v2/categories"
        # Buscar si ya existe
        resp = requests.get(url, headers=_auth_header(), params={"search": name, "per_page": 5}, timeout=10)
        resp.raise_for_status()
        for cat in resp.json():
            if cat["name"].lower() == name.lower():
                return cat["id"]
        # Crear si no existe
        headers = {**_auth_header(), "Content-Type": "application/json"}
        resp = requests.post(url, data=json.dumps({"name": name}), headers=headers, timeout=10)
        resp.raise_for_status()
        cat_id = resp.json().get("id")
        logger.info(f"WordPress: categoría creada '{name}' ID={cat_id}")
        return cat_id
    except Exception as e:
        logger.warning(f"WordPress get_or_create_category('{name}') error: {e}")
        return None


def create_post(
    title: str,
    body_html: str,
    original_url: str,
    source_name: str,
    featured_media_id: int = None,
    sticky: bool = False,
    categories: list = None,
) -> str | None:
    """
    Crea un post en WordPress.
    Retorna (post_id, post_url) o (None, None) si falla.
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
            "sticky": sticky,
        }
        if featured_media_id:
            payload["featured_media"] = featured_media_id
        if categories:
            payload["categories"] = categories

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


def get_posts_by_category(category_id: int, per_page: int = 20) -> list[dict]:
    """Retorna posts de una categoría ordenados por fecha desc."""
    try:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts"
        params = {"categories": category_id, "per_page": per_page, "orderby": "date", "order": "desc", "status": "publish"}
        resp = requests.get(url, headers=_auth_header(), params=params, timeout=15)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.warning(f"WordPress get_posts_by_category({category_id}) error: {e}")
        return []


def delete_post(post_id: int) -> bool:
    """Elimina un post de WordPress (lo mueve a papelera)."""
    try:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts/{post_id}"
        resp = requests.delete(url, headers=_auth_header(), params={"force": True}, timeout=15)
        resp.raise_for_status()
        logger.info(f"WordPress: post ID={post_id} eliminado")
        return True
    except Exception as e:
        logger.warning(f"WordPress delete_post({post_id}) error: {e}")
        return False


def get_sticky_post_ids() -> list[int]:
    """Retorna los IDs de todos los posts actualmente marcados como sticky."""
    try:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts"
        params = {"sticky": True, "per_page": 20, "status": "publish"}
        resp = requests.get(url, headers=_auth_header(), params=params, timeout=15)
        resp.raise_for_status()
        return [p["id"] for p in resp.json()]
    except Exception as e:
        logger.warning(f"WordPress get_sticky_post_ids error: {e}")
        return []


def set_sticky(post_id: int, sticky: bool) -> bool:
    """Cambia el estado sticky de un post existente."""
    try:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts/{post_id}"
        headers = {**_auth_header(), "Content-Type": "application/json"}
        resp = requests.post(url, data=json.dumps({"sticky": sticky}), headers=headers, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning(f"WordPress set_sticky({post_id}, {sticky}) error: {e}")
        return False


def rotate_sticky_posts(new_post_ids: list[int], max_sticky: int = 4):
    """
    Quita el sticky a los posts actuales y marca como sticky los nuevos IDs.
    Mantiene hasta max_sticky posts fijados en total.
    """
    current = get_sticky_post_ids()
    for pid in current:
        set_sticky(pid, False)
        logger.info(f"WordPress: sticky quitado a post ID={pid}")

    for pid in new_post_ids[:max_sticky]:
        set_sticky(pid, True)
        logger.info(f"WordPress: post ID={pid} marcado como destacado (sticky)")
