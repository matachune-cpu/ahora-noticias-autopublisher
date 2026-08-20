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
    """Usa Gemini para generar caption_facebook e caption_instagram.

    Lanza excepción si Gemini falla — el caller decide si saltear el artículo.
    Nunca devuelve solo el título como fallback silencioso.
    """
    from google import genai
    from google.genai import types

    logger.info(f"  Generando captions — body_text: {len(body_text)} chars")
    if len(body_text) < 50:
        raise ValueError(f"body_text demasiado corto para generar captions: {len(body_text)} chars")

    key = os.getenv("GEMINI_API_KEY")
    client = genai.Client(api_key=key)

    prompt = f"""Sos redactor senior de Ahora Noticias (Santiago del Estero, Argentina).
Tu tarea: escribir DOS textos para publicar en redes sociales basándote EXCLUSIVAMENTE en el contenido de la nota que te paso.

TÍTULO DE LA NOTA: {title}

CONTENIDO DE LA NOTA:
{body_text}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEXTO 1 — FACEBOOK (campo: caption_facebook)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Estructura OBLIGATORIA con saltos de línea entre cada bloque:

LÍNEA 1 (HOOK): Una oración sola. Dato duro, cifra o hecho concreto que golpee. Sin rodeos. Ejemplos: "Tenía 3 años y no llegó a tiempo." / "50.000 jubilados perdieron el bono de un día para el otro." / "Lo atraparon con 200 kilos de droga a 10 km del centro."

[línea vacía]

PÁRRAFO 2 (EL HECHO): 2-3 oraciones cortas. Quién, qué, cuándo, dónde. Toda la info concreta de la nota.

[línea vacía]

PÁRRAFO 3 (CONTEXTO): 1-2 oraciones. Qué significa esto, qué antecedentes hay, qué viene después.

[línea vacía]

PREGUNTA FINAL: Una pregunta directa al lector que genere debate o reflexión. Ejemplos: "¿Qué opinás de esta medida?" / "¿Creés que se va a hacer justicia?" / "¿Sabías que esto estaba pasando en Santiago?"

REGLAS ESTRICTAS:
- SIN hashtags
- SIN mencionar la fuente original (ni Infobae, ni El Liberal, ni ningún otro medio)
- NO invitar a visitar la web — el link se agrega automáticamente aparte
- Tono periodístico directo, como habla un santiagueño
- Máximo 450 caracteres en total

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
TEXTO 2 — INSTAGRAM (campo: caption_instagram)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

IMPORTANTE: En Instagram el usuario DEBE poder leer la noticia COMPLETA acá. No hay link a la web. La persona se tiene que informar leyendo este texto solo.

Estructura OBLIGATORIA con saltos de línea entre cada bloque:

LÍNEA 1 (GANCHO): Una oración que haga parar el scroll. El dato más impactante de la nota.

[línea vacía]

PÁRRAFO 2 (LA NOTICIA): 3-4 oraciones. Contá TODO lo importante: quién, qué pasó, cuándo, dónde, cómo. El lector tiene que quedar informado leyendo esto.

[línea vacía]

PÁRRAFO 3 (CONTEXTO): 2-3 oraciones. Antecedentes, consecuencias, qué cambia a partir de esto.

[línea vacía]

PREGUNTA FINAL: Una pregunta que invite a opinar o reflexionar.

[línea vacía]

HASHTAGS: 4-5 hashtags relevantes al tema (#SantiagoDelEstero u otros según corresponda)

REGLAS ESTRICTAS:
- NUNCA escribir "visitá nuestra web", "leé la nota completa", "link en bio", "entrá a nuestro sitio" ni ninguna invitación al sitio web
- NUNCA mencionar la fuente original
- El texto debe ser autosuficiente: quien lo lee queda completamente informado
"""

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
    fb = data.get("caption_facebook", "").strip()
    ig = data.get("caption_instagram", "").strip()

    if not fb or not ig:
        raise ValueError(f"Gemini devolvió captions vacíos: fb={len(fb)} ig={len(ig)}")

    logger.info(f"  Caption FB ({len(fb)} chars): {fb[:100]}...")
    logger.info(f"  Caption IG ({len(ig)} chars): {ig[:100]}...")
    return {"facebook": fb, "instagram": ig}


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
    try:
        captions = generar_captions(title, body_text, source)
    except Exception as e:
        logger.error(f"  No se pudieron generar captions: {e} — saltando artículo")
        return False

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


def reset_social_posts(max_items: int):
    """Borra los últimos N posts de FB/IG y resetea la DB para republicarlos."""
    from publishers.facebook import delete_post as fb_delete

    with sqlite3.connect(database.DB_PATH) as conn:
        rows = conn.execute(
            """
            SELECT original_url, title, fb_post_id, ig_post_id
            FROM articles
            WHERE fb_post_id IS NOT NULL AND fb_post_id != ''
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (max_items,),
        ).fetchall()

    if not rows:
        logger.info("No hay posts recientes en redes para borrar.")
        return

    logger.info(f"Borrando {len(rows)} posts de Facebook...")
    for url, title, fb_post_id, ig_post_id in rows:
        logger.info(f"  Borrando FB post {fb_post_id}: {title[:60]}")
        ok = fb_delete(fb_post_id)
        logger.info(f"  {'OK' if ok else 'FALLÓ (ya puede estar borrado)'}")

        # Resetear en DB
        with sqlite3.connect(database.DB_PATH) as conn:
            conn.execute(
                "UPDATE articles SET fb_post_id = NULL, ig_post_id = NULL WHERE url_hash = ?",
                (database.url_hash(url),),
            )
            conn.commit()

    logger.info(f"DB reseteada. {len(rows)} artículos listos para republicar.")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=10,
                        help="Máximo de artículos a publicar en redes (default: 10)")
    parser.add_argument("--delay-minutes", type=int, default=0,
                        help="Minutos de espera entre cada publicación (default: 0)")
    parser.add_argument("--reset", action="store_true",
                        help="Borrar los últimos posts en redes y resetear DB antes de publicar")
    args = parser.parse_args()

    database.init_db()

    if args.reset:
        logger.info("Modo RESET: borrando posts anteriores...")
        reset_social_posts(args.max)
        logger.info("Reset completado. Iniciando republicación...")

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

        # Pausa entre publicaciones
        if args.delay_minutes > 0 and i < len(articles):
            logger.info(f"  Esperando {args.delay_minutes} minuto(s) antes del siguiente...")
            import time
            time.sleep(args.delay_minutes * 60)

    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"Completado: {ok} publicados en redes, {fail} fallaron o sin imagen")


if __name__ == "__main__":
    main()
