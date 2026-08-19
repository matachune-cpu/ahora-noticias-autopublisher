"""
Publica en Facebook e Instagram los artículos que ya están en WordPress
pero que no llegaron a redes sociales (ej: por falta de imagen en el momento).

Uso:
    python _publicar_redes.py [--max 10]

Flujo por artículo:
    1. Lee la DB: artículos con wp_post_id pero sin fb_post_id
    2. Verifica que el post de WP tiene imagen destacada (featured_media)
    3. Genera captions FB e IG con Gemini a partir del contenido del post
    4. Publica en Facebook (foto + caption + link)
    5. Genera flyer y publica en Instagram
    6. Actualiza la DB
"""
import argparse
import base64
import json
import logging
import os
import re
import sqlite3
import tempfile
from datetime import datetime

from dotenv import load_dotenv
load_dotenv()

import requests
from bs4 import BeautifulSoup

import config
import database
from publishers import facebook, instagram
from publishers.wordpress import upload_image
from flyer_generator import generate_flyer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("publicar_redes")


def _auth():
    creds = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    return {"Authorization": f"Basic {base64.b64encode(creds.encode()).decode()}"}


def get_pending_articles(max_items: int) -> list[dict]:
    """Artículos con WP post pero sin publicación en redes sociales."""
    with sqlite3.connect(database.DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT original_url, title, source, wp_post_id
            FROM articles
            WHERE wp_post_id IS NOT NULL
              AND wp_post_id != ''
              AND (fb_post_id IS NULL OR fb_post_id = '')
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max_items,),
        ).fetchall()
    return [
        {"url": r[0], "title": r[1], "source": r[2], "wp_post_id": r[3]}
        for r in rows
    ]


def get_wp_post(wp_post_id: str) -> dict:
    """Obtiene datos del post de WP: imagen destacada, link, contenido."""
    try:
        resp = requests.get(
            f"{config.WP_URL}/wp-json/wp/v2/posts/{wp_post_id}",
            headers=_auth(),
            params={"_fields": "id,title,link,featured_media,content,source"},
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        logger.error(f"  WP get_post error: {e}")
        return {}


def get_media_url(media_id: int) -> str:
    """Obtiene la URL de la imagen de la media library de WP."""
    try:
        resp = requests.get(
            f"{config.WP_URL}/wp-json/wp/v2/media/{media_id}",
            headers=_auth(),
            params={"_fields": "source_url"},
            timeout=10,
        )
        resp.raise_for_status()
        return resp.json().get("source_url", "")
    except Exception:
        return ""


def _html_to_text(html: str) -> str:
    """Extrae texto plano del HTML del post (sin el pie de atribución)."""
    soup = BeautifulSoup(html, "html.parser")
    # Remover el párrafo de atribución
    for p in soup.find_all("p"):
        if "Fuente original" in p.get_text():
            p.decompose()
    return soup.get_text(separator=" ", strip=True)[:6000]


def generar_captions(title: str, body_text: str, source: str) -> dict:
    """Usa Gemini para generar caption_facebook e caption_instagram."""
    from google import genai
    from google.genai import types

    key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=key)

    prompt = f"""Sos redactor de Ahora Noticias (Santiago del Estero, Argentina).
Generá DOS captions para redes sociales de esta nota, en base al título y contenido.

TÍTULO: {title}
FUENTE: {source}
CONTENIDO: {body_text}

REGLAS CAPTION FACEBOOK:
- Primera línea = gancho emocional puro: dato impactante, cifra, nombre + hecho, verbo fuerte
- EJEMPLOS buenos: "Tenía 3 años y no llegó a tiempo." / "El gobierno le cortó la beca a 50.000 jóvenes."
- 2-3 oraciones con dato concreto
- Cierra con pregunta que invite a comentar
- SIN hashtags. Máximo 450 caracteres total.

REGLAS CAPTION INSTAGRAM:
- Primera línea = GOLPE EMOCIONAL antes del "ver más": dato duro, cifra, nombre + hecho visceral
- 2-4 oraciones con los datos más importantes, tono directo
- Termina SIEMPRE con pregunta al lector
- Máximo 5 hashtags relevantes al final
- NO usar "Te contamos", "Enterate", "La noticia de hoy"
"""

    try:
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "caption_facebook": {"type": "string"},
                        "caption_instagram": {"type": "string"},
                    },
                    "required": ["caption_facebook", "caption_instagram"],
                },
                temperature=0.7,
            ),
        )
        data = json.loads(response.text)
        return {
            "facebook": data.get("caption_facebook", title),
            "instagram": data.get("caption_instagram", title),
        }
    except Exception as e:
        logger.warning(f"  Gemini captions error: {e} — usando título como caption")
        return {"facebook": title, "instagram": title}


def update_db_social(url: str, fb_post_id: str, ig_post_id: str):
    """Actualiza la DB con los IDs de publicación social."""
    with sqlite3.connect(database.DB_PATH) as conn:
        conn.execute(
            """UPDATE articles
               SET fb_post_id = ?, ig_post_id = ?
               WHERE url_hash = ?""",
            (fb_post_id, ig_post_id, database.url_hash(url)),
        )
        conn.commit()


def publicar_en_redes(article: dict) -> bool:
    url = article["url"]
    title = article["title"]
    source = article["source"] or "Fuente"
    wp_post_id = article["wp_post_id"]

    logger.info(f"━━ {title[:70]}")

    # 1. Obtener datos del post de WP
    wp_post = get_wp_post(wp_post_id)
    if not wp_post:
        logger.warning(f"  No se pudo obtener post WP #{wp_post_id}")
        return False

    media_id = wp_post.get("featured_media", 0)
    if not media_id:
        logger.warning(f"  Post #{wp_post_id} sigue sin imagen — saltando")
        return False

    wp_post_url = wp_post.get("link", "")
    content_html = wp_post.get("content", {}).get("rendered", "")

    # 2. Obtener URL de la imagen destacada
    image_url = get_media_url(media_id)
    if not image_url:
        logger.warning(f"  No se pudo obtener URL de media ID={media_id}")
        return False

    logger.info(f"  Imagen: {image_url[:80]}")

    # 3. Generar captions con Gemini
    body_text = _html_to_text(content_html)
    captions = generar_captions(title, body_text, source)
    logger.info(f"  Caption FB: {captions['facebook'][:80]}...")

    # 4. Publicar en Facebook
    fb_post_id = facebook.post_link(
        title=title,
        wp_post_url=wp_post_url,
        original_url=url,
        image_url=image_url,
        caption=captions["facebook"],
    )
    logger.info(f"  Facebook: {'OK ID=' + str(fb_post_id) if fb_post_id else 'FALLÓ'}")

    # 5. Generar flyer e Instagram
    ig_post_id = None
    flyer_path = None
    flyer_url = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name
        generate_flyer(
            title=title,
            source_name=source,
            article_image_url=image_url,
            template_path=config.FLYER_TEMPLATE_PATH,
            output_path=flyer_path,
            categoria="",
        )
        _, flyer_url = upload_image(
            image_path=flyer_path,
            filename=f"flyer-redes-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        )
        logger.info(f"  Flyer: {flyer_url[:70] if flyer_url else 'falló'}")
    except Exception as e:
        logger.error(f"  Error generando flyer: {e}")
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

    if flyer_url:
        try:
            ig_post_id = instagram.post_image(
                image_path=None,
                caption=captions["instagram"],
                public_image_url=flyer_url,
            )
            logger.info(f"  Instagram: {'OK ID=' + str(ig_post_id) if ig_post_id else 'FALLÓ'}")
        except Exception as e:
            logger.error(f"  Error en Instagram: {e}")

    # 6. Actualizar DB
    if fb_post_id or ig_post_id:
        update_db_social(url, str(fb_post_id) if fb_post_id else None, str(ig_post_id) if ig_post_id else None)
        logger.info(f"  DB actualizada.")
        return True

    return False


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=10,
                        help="Máximo de artículos a publicar en redes (default: 10)")
    args = parser.parse_args()

    database.init_db()

    logger.info(f"Buscando artículos sin publicación en redes (máx {args.max})...")
    articles = get_pending_articles(args.max)
    logger.info(f"Encontrados: {len(articles)} artículos pendientes")

    if not articles:
        logger.info("Todo al día en redes sociales.")
        return

    ok = 0
    fail = 0
    for i, article in enumerate(articles, 1):
        logger.info(f"[{i}/{len(articles)}]")
        try:
            if publicar_en_redes(article):
                ok += 1
            else:
                fail += 1
        except Exception as e:
            logger.error(f"  Error inesperado: {e}")
            fail += 1

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"Completado: {ok} publicados en redes, {fail} fallaron o sin imagen")


if __name__ == "__main__":
    main()
