"""
Busca posts de WordPress sin imagen destacada y les agrega una.
Extrae la URL original de la fuente del contenido del post y la usa para resolver la imagen.

Uso:
    python _fix_images.py [--max 50]
"""
import argparse
import json
import logging
import os
import re
import sys
import time

from dotenv import load_dotenv
load_dotenv()

import requests
import base64
from bs4 import BeautifulSoup

import config
from image_resolver import resolve_news_image

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("fix_images")


def _auth():
    creds = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    token = base64.b64encode(creds.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def get_posts_without_image(max_posts: int) -> list[dict]:
    """Devuelve posts publicados sin imagen destacada con su contenido."""
    results = []
    page = 1
    per_page = 50

    while len(results) < max_posts:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts"
        params = {
            "status": "publish",
            "per_page": per_page,
            "page": page,
            "_fields": "id,title,link,featured_media,content",
            "orderby": "date",
            "order": "desc",
        }
        resp = requests.get(url, params=params, headers=_auth(), timeout=20)
        if resp.status_code == 400:
            break
        resp.raise_for_status()
        posts = resp.json()
        if not posts:
            break

        for p in posts:
            if p.get("featured_media", 0) == 0:
                content_html = p.get("content", {}).get("rendered", "")
                original_url = _extract_source_url(content_html)
                results.append({
                    "id": p["id"],
                    "title": p["title"]["rendered"],
                    "link": p["link"],
                    "original_url": original_url,
                })
            if len(results) >= max_posts:
                break

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1

    return results


def _extract_source_url(content_html: str) -> str:
    """
    Extrae la URL de la fuente original del HTML de atribución al pie del post.
    Formato: <a href="URL" target="_blank" rel="noopener">Fuente</a>
    """
    try:
        soup = BeautifulSoup(content_html, "html.parser")
        # Buscar el párrafo de atribución "Fuente original:"
        for p in soup.find_all("p"):
            text = p.get_text()
            if "Fuente original" in text or "fuente original" in text:
                a = p.find("a", href=True)
                if a and a["href"].startswith("http"):
                    return a["href"]
        # Fallback: cualquier enlace externo (no ahoranoticias)
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if href.startswith("http") and "ahoranoticias" not in href:
                return href
    except Exception:
        pass
    return ""


def _extract_og_image(url: str) -> str:
    """Scrape directo de og:image de una URL."""
    try:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
        }
        resp = requests.get(url, headers=headers, timeout=12, allow_redirects=True)
        if resp.status_code != 200:
            return ""
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return tag["content"]
    except Exception as e:
        logger.debug(f"  og:image scrape error: {e}")
    return ""


def upload_image(image_url: str, filename: str) -> tuple:
    try:
        r = requests.get(image_url, timeout=15,
                         headers={"User-Agent": "Mozilla/5.0"})
        r.raise_for_status()
        ct = r.headers.get("Content-Type", "image/jpeg")
        ext = "jpg" if "jpeg" in ct or "jpg" in ct else ct.split("/")[-1]
        headers = {
            **_auth(),
            "Content-Disposition": f'attachment; filename="{filename}.{ext}"',
            "Content-Type": "image/jpeg",
        }
        resp = requests.post(
            f"{config.WP_URL}/wp-json/wp/v2/media",
            headers=headers,
            data=r.content,
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        return data["id"], data.get("source_url", "")
    except Exception as e:
        logger.error(f"  upload_image error: {e}")
        return None, None


def update_post_image(post_id: int, media_id: int) -> bool:
    try:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts/{post_id}"
        headers = {**_auth(), "Content-Type": "application/json"}
        resp = requests.post(
            url,
            headers=headers,
            data=json.dumps({"featured_media": media_id}),
            timeout=20,
        )
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.error(f"  update_post error: {e}")
        return False


def fix_post(post: dict) -> bool:
    title = post["title"]
    post_id = post["id"]
    original_url = post.get("original_url", "")

    logger.info(f"━━ Post #{post_id}: {title[:70]}")
    logger.info(f"   Fuente original: {original_url[:80] if original_url else '(no encontrada)'}")

    image_url = None

    # Estrategia 1: scrape directo de og:image de la fuente original
    if original_url:
        og = _extract_og_image(original_url)
        if og:
            logger.info(f"   og:image directo: {og[:80]}")
            image_url = og

    # Estrategia 2: image_resolver con la URL original como article_url
    if not image_url:
        img_result = resolve_news_image(
            title=title,
            summary="",
            article_url=original_url or post["link"],
            article_image_url=None,
        )
        if img_result["status"] == "VALIDATED":
            image_url = img_result["image_url"]
            logger.info(f"   image_resolver: {image_url[:80]}")

    if not image_url:
        logger.warning(f"   Sin imagen encontrada — saltando.")
        return False

    media_id, media_url = upload_image(image_url, f"foto-post-{post_id}")
    if not media_id:
        logger.error(f"   No se pudo subir la imagen.")
        return False

    ok = update_post_image(post_id, media_id)
    if ok:
        logger.info(f"   OK — Post #{post_id} actualizado con imagen.")
    else:
        logger.error(f"   Error al actualizar el post.")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=100)
    args = parser.parse_args()

    logger.info(f"Buscando posts sin imagen (máx {args.max})...")
    posts = get_posts_without_image(args.max)
    logger.info(f"Encontrados: {len(posts)} posts sin imagen destacada")

    if not posts:
        logger.info("Nada que corregir.")
        return

    fixed = 0
    skipped = 0
    for i, post in enumerate(posts, 1):
        logger.info(f"[{i}/{len(posts)}]")
        ok = fix_post(post)
        if ok:
            fixed += 1
        else:
            skipped += 1
        if i < len(posts):
            time.sleep(1)

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"Completado: {fixed} posts con imagen nueva, {skipped} sin imagen encontrada")


if __name__ == "__main__":
    main()
