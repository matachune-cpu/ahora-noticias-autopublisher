"""
Elimina un post de WordPress por su URL slug.
Uso: python _eliminar_post.py --slug "el-pp-avisa-a-los-ministros..."
"""
import argparse
import logging
import requests
import base64
from dotenv import load_dotenv

load_dotenv()

import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("eliminar_post")


def _auth_header():
    credentials = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def eliminar_por_slug(slug: str):
    # Buscar el post por slug
    url = f"{config.WP_URL}/wp-json/wp/v2/posts"
    resp = requests.get(url, headers=_auth_header(), params={"slug": slug, "status": "publish"}, timeout=15)
    resp.raise_for_status()
    posts = resp.json()

    if not posts:
        logger.warning(f"No se encontró ningún post con slug: {slug}")
        return

    for post in posts:
        pid = post["id"]
        title = post.get("title", {}).get("rendered", "")[:80]
        del_resp = requests.delete(
            f"{config.WP_URL}/wp-json/wp/v2/posts/{pid}",
            headers=_auth_header(),
            params={"force": True},
            timeout=15,
        )
        if del_resp.status_code in (200, 204):
            logger.info(f"✓ Eliminado ID={pid}: {title}")
        else:
            logger.error(f"✗ Error {del_resp.status_code} al eliminar ID={pid}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--slug", required=True, help="Slug del post (parte final de la URL)")
    args = parser.parse_args()
    eliminar_por_slug(args.slug)
