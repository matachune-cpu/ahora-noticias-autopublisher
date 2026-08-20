"""
Publicación directa a WordPress sin IA.
Modo de emergencia cuando Gemini tiene cuota agotada.

Flujo:
  1. Scrapea artículos de todas las fuentes configuradas
  2. Publica en WP con el texto original limpio (sin reescritura)
  3. Omite completamente Facebook, Instagram y WhatsApp

Uso:
    python _publicar_sin_ia.py [--max 10]
"""
import argparse
import logging
import re
import time
import unicodedata
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

import config
import database
from scraper import fetch_entries, extract_article
from publishers import wordpress

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("publicar_sin_ia")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

MIN_CHARS = 300
DEDUP_THRESHOLD = 0.45
DEDUP_HOURS = 12

_STOPWORDS = {
    "el","la","los","las","un","una","de","del","al","en","con","por","para",
    "que","se","lo","le","y","o","a","es","son","fue","ha","hay","no","si",
    "ya","pero","como","este","esta","ese","esa","todo","cada","nuevo","nueva",
}


def _palabras(titulo: str) -> set:
    s = unicodedata.normalize("NFD", titulo)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return {p for p in s.split() if len(p) > 3 and p not in _STOPWORDS}


def _jaccard(a: str, b: str) -> float:
    wa, wb = _palabras(a), _palabras(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _es_duplicado(titulo: str, recientes: list[str]) -> bool:
    return any(_jaccard(titulo, t) >= DEDUP_THRESHOLD for t in recientes)


def _get_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return tag["content"]
    except Exception:
        pass
    return None


def _build_body_html(text: str, source_name: str, original_url: str) -> str:
    parrafos = [p.strip() for p in text.split("\n") if len(p.strip()) > 40]
    if not parrafos:
        parrafos = [text.strip()]
    cuerpo = "\n".join(f"<p>{p}</p>" for p in parrafos[:18])
    pie = (
        f'<p><em>Fuente original: '
        f'<a href="{original_url}" target="_blank" rel="noopener">{source_name}</a></em></p>'
    )
    return cuerpo + "\n" + pie


def run(max_articles: int = 10):
    database.init_db()
    logger.info(f"=== Publicación sin IA — máx {max_articles} artículos ===")

    titulos_recientes = database.get_recent_titles(hours=DEDUP_HOURS)
    logger.info(f"Deduplicador: {len(titulos_recientes)} títulos en últimas {DEDUP_HOURS}h")

    publicados = 0
    nuevos_ids = []

    for source in config.NEWS_SOURCES:
        if publicados >= max_articles:
            break

        logger.info(f"Fuente: {source['name']}")
        entries = fetch_entries(source, max_items=source.get("max_articles", 5))

        for entry in entries:
            if publicados >= max_articles:
                break

            url = entry.get("url", "").strip()
            title = entry.get("title", "").strip()

            if not url or len(title) < 10:
                continue
            if database.is_published(url):
                continue
            if _es_duplicado(title, titulos_recientes):
                logger.info(f"  [DEDUP] {title[:60]}")
                database.mark_seen(url, title, source["name"])
                continue

            article = extract_article(
                url, source["name"], title, entry.get("summary", ""),
                full_text=entry.get("full_text"),
                image_url=entry.get("image_url"),
            )
            if not article or len((article.full_text or "").strip()) < MIN_CHARS:
                database.mark_seen(url, title, source["name"])
                continue

            # Imagen: usar la del artículo o buscar og:image directamente
            image_url = article.image_url or _get_og_image(url)

            media_id = None
            if image_url:
                try:
                    media_id, _ = wordpress.upload_image(
                        image_url=image_url,
                        filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
                    )
                except Exception as e:
                    logger.warning(f"  Imagen no se pudo subir: {e}")

            body_html = _build_body_html(article.full_text, source["name"], url)

            try:
                wp_post_id, wp_post_url = wordpress.create_post(
                    title=title,
                    body_html=body_html,
                    original_url=url,
                    source_name=source["name"],
                    featured_media_id=media_id,
                )
            except Exception as e:
                logger.error(f"  WP error: {e}")
                database.mark_seen(url, title, source["name"])
                continue

            if wp_post_id:
                database.mark_published(url=url, title=title, source=source["name"],
                                        wp_post_id=str(wp_post_id))
                titulos_recientes.append(title)
                nuevos_ids.append(int(wp_post_id))
                publicados += 1
                provincia = source.get("provincia", "")
                logger.info(
                    f"  ✓ [{provincia or 'Nacional'}] {title[:60]} | WP ID={wp_post_id}"
                )
            else:
                database.mark_seen(url, title, source["name"])

            time.sleep(2)

        time.sleep(2)

    logger.info(f"=== Completado: {publicados} publicados ===")

    if nuevos_ids:
        logger.info(f"Actualizando encabezado: {len(nuevos_ids)} artículo(s) nuevos → sticky (máx 4)")
        wordpress.rotate_sticky_posts(nuevos_ids, max_sticky=4)

    return publicados


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=10,
                        help="Máximo de artículos a publicar (default: 10)")
    args = parser.parse_args()
    run(args.max)
