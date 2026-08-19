"""
Busca posts de WordPress sin imagen destacada y les agrega una.

Uso:
    python _fix_images.py [--max 50] [--dry-run]

--max N    : procesar máximo N posts sin imagen (default: 100)
--dry-run  : mostrar qué haría sin hacer cambios reales
"""
import argparse
import logging
import os
import sys
import time

from dotenv import load_dotenv
load_dotenv()

import requests
import base64

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
    """Devuelve posts publicados sin imagen destacada (featured_media == 0)."""
    results = []
    page = 1
    per_page = 50

    while len(results) < max_posts:
        url = f"{config.WP_URL}/wp-json/wp/v2/posts"
        params = {
            "status": "publish",
            "per_page": per_page,
            "page": page,
            "_fields": "id,title,link,featured_media",
            "orderby": "date",
            "order": "desc",
        }
        resp = requests.get(url, params=params, headers=_auth(), timeout=20)
        if resp.status_code == 400:
            break  # sin más páginas
        resp.raise_for_status()
        posts = resp.json()
        if not posts:
            break

        for p in posts:
            if p.get("featured_media", 0) == 0:
                results.append({
                    "id": p["id"],
                    "title": p["title"]["rendered"],
                    "link": p["link"],
                })
            if len(results) >= max_posts:
                break

        total_pages = int(resp.headers.get("X-WP-TotalPages", 1))
        if page >= total_pages:
            break
        page += 1

    return results


def upload_image(image_url: str, filename: str) -> tuple:
    try:
        r = requests.get(image_url, timeout=15)
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
        import json
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


def fix_post(post: dict, dry_run: bool) -> bool:
    title = post["title"]
    post_id = post["id"]
    link = post["link"]

    logger.info(f"━━ Post #{post_id}: {title[:70]}")

    img_result = resolve_news_image(
        title=title,
        summary="",
        article_url=link,
        article_image_url=None,
    )

    if img_result["status"] != "VALIDATED":
        reasons = img_result.get("rejection_reasons", [])
        logger.warning(f"  Sin imagen validada: {reasons}")
        return False

    image_url = img_result["image_url"]
    strategy = img_result["strategy"]
    score = img_result["final_score"]
    logger.info(f"  Imagen encontrada | estrategia={strategy} score={score:.0f} | {image_url[:70]}")

    if dry_run:
        logger.info(f"  [DRY-RUN] No se sube nada.")
        return True

    media_id, media_url = upload_image(image_url, f"foto-post-{post_id}")
    if not media_id:
        logger.error(f"  No se pudo subir la imagen.")
        return False

    ok = update_post_image(post_id, media_id)
    if ok:
        logger.info(f"  ✓ Post #{post_id} actualizado con imagen.")
    else:
        logger.error(f"  Error al actualizar el post.")
    return ok


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=100, help="Máximo de posts a procesar")
    parser.add_argument("--dry-run", action="store_true", help="No hacer cambios reales")
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
        ok = fix_post(post, dry_run=args.dry_run)
        if ok:
            fixed += 1
        else:
            skipped += 1
        # Pausa entre llamadas a Gemini para no saturar la API
        if i < len(posts):
            time.sleep(2)

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"Completado: {fixed} posts con imagen nueva, {skipped} sin imagen encontrada")


if __name__ == "__main__":
    main()
