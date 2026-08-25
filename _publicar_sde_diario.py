"""
Pasada diaria de noticias de Santiago del Estero.
Corre una vez al día, publica hasta 8 artículos locales y deja el más
importante como Destacado (sticky) en el hero del sitio.

Prioridad de importancia: El Liberal > Gobierno SDE > Santiago Ciudad > La Banda

Uso:
    python _publicar_sde_diario.py [--max 8]
"""
import argparse
import logging
import re
import time
import unicodedata
from datetime import datetime
from urllib.parse import urlparse

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
logger = logging.getLogger("publicar_sde_diario")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

MIN_CHARS = 300
DEDUP_THRESHOLD = 0.45
DEDUP_HOURS = 12

# Fuentes de Santiago del Estero filtradas de config.NEWS_SOURCES
_SDE_SOURCE_NAMES = {
    "El Liberal", "Gobierno SDE", "Santiago Ciudad", "Municipalidad La Banda"
}

# Orden de prioridad para elegir el Destacado
_PRIORIDAD_FUENTE = {
    "El Liberal": 1,
    "Gobierno SDE": 2,
    "Santiago Ciudad": 3,
    "Municipalidad La Banda": 4,
}

_STOPWORDS = {
    "el","la","los","las","un","una","de","del","al","en","con","por","para",
    "que","se","lo","le","y","o","a","es","son","fue","ha","hay","no","si",
    "ya","pero","como","este","esta","ese","esa","todo","cada","nuevo","nueva",
}

_LOGO_URL_SIGNALS = (
    "logo", "default-image", "placeholder", "no-image", "noimage",
    "default_image", "favicon", "apple-touch", "og-default", "share-default",
    "brand/", "/brand-", "watermark",
)

_categoria_id_cache: dict[str, int] = {}


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


def _imagen_es_logo(url: str) -> bool:
    if not url:
        return True
    return any(s in url.lower() for s in _LOGO_URL_SIGNALS)


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


def _get_categoria_id(nombre: str) -> int | None:
    if nombre in _categoria_id_cache:
        return _categoria_id_cache[nombre]
    cat_id = wordpress.get_or_create_category(nombre)
    if cat_id:
        _categoria_id_cache[nombre] = cat_id
    return cat_id


def run(max_articles: int = 8):
    database.init_db()
    logger.info(f"=== Pasada SDE diaria — máx {max_articles} artículos ===")

    titulos_recientes = database.get_recent_titles(hours=DEDUP_HOURS)

    sde_sources = [s for s in config.NEWS_SOURCES if s["name"] in _SDE_SOURCE_NAMES]
    logger.info(f"Fuentes SDE: {[s['name'] for s in sde_sources]}")

    publicados = 0
    nuevos_ids: list[tuple[int, str, str]] = []  # (wp_id, title, source_name)

    for source in sde_sources:
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

            if database.is_seen(url):
                continue
            if _es_duplicado(title, titulos_recientes):
                logger.info(f"  [DUP] {title[:60]}")
                database.mark_seen(url, title, source["name"])
                continue

            # Extraer contenido
            article = extract_article(url, source)
            if not article:
                continue

            text = article.get("text", "").strip()
            if len(text) < MIN_CHARS:
                logger.info(f"  [CORTO] {len(text)} chars — {title[:55]}")
                database.mark_seen(url, title, source["name"])
                continue

            # Imagen destacada
            img_url = article.get("image_url") or entry.get("image_url") or _get_og_image(url)
            if _imagen_es_logo(img_url):
                img_url = None

            img_id = None
            if img_url:
                try:
                    img_id = wordpress.upload_image(img_url, title)
                except Exception as e:
                    logger.warning(f"  Imagen fallida: {e}")

            # Categoría: Santiago del Estero
            cat_id = _get_categoria_id("Santiago del Estero")
            categories = [cat_id] if cat_id else []

            body_html = _build_body_html(text, source["name"], url)

            try:
                wp_result = wordpress.create_post(
                    title=title,
                    content=body_html,
                    status="publish",
                    featured_media=img_id,
                    sticky=False,
                    categories=categories,
                )
            except Exception as e:
                logger.error(f"  Error WP: {e}")
                continue

            if not wp_result:
                continue

            wp_id = wp_result.get("id")
            if not wp_id:
                continue

            database.mark_seen(url, title, source["name"])
            titulos_recientes.append(title)
            publicados += 1
            nuevos_ids.append((wp_id, title, source["name"]))
            logger.info(f"  ✓ [{source['name']}] {title[:65]} (ID={wp_id})")
            time.sleep(1)

    logger.info(f"\nPublicados en SDE diario: {publicados}")

    if not nuevos_ids:
        logger.info("Sin artículos nuevos — nada que destacar.")
        return

    # Elegir el más importante para Destacado
    def prioridad(item):
        _, _, sname = item
        return _PRIORIDAD_FUENTE.get(sname, 99)

    mejor = sorted(nuevos_ids, key=prioridad)[0]
    mejor_id, mejor_title, mejor_fuente = mejor

    logger.info(f"\nDestacando: [{mejor_fuente}] {mejor_title[:65]} (ID={mejor_id})")
    try:
        wordpress.set_sticky(mejor_id, True)
        wordpress.rotate_sticky_posts(max_sticky=4)
        logger.info("  ✓ Sticky aplicado y rotación ejecutada")
    except Exception as e:
        logger.error(f"  Error al destacar: {e}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=8)
    args = parser.parse_args()
    run(max_articles=args.max)
