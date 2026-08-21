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


def eliminar_por_id(post_id: int):
    del_resp = requests.delete(
        f"{config.WP_URL}/wp-json/wp/v2/posts/{post_id}",
        headers=_auth_header(),
        params={"force": True},
        timeout=15,
    )
    if del_resp.status_code in (200, 204):
        logger.info(f"✓ Eliminado ID={post_id}")
    else:
        logger.error(f"✗ Error {del_resp.status_code} al eliminar ID={post_id}: {del_resp.text[:200]}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--slug", help="Slug del post (parte final de la URL)")
    group.add_argument("--id", type=int, help="ID numérico del post en WordPress")
    args = parser.parse_args()
    if args.slug:
        eliminar_por_slug(args.slug)
    else:
        eliminar_por_id(args.id)
