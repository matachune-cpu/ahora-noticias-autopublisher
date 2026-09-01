"""
Barrido federal diario: garantiza al menos 1 nota de CADA provincia argentina.
Corre una vez al día antes que el cron horario, de Tierra del Fuego a Jujuy.

Criterio de selección por provincia:
  1. Artículo que mencione explícitamente la provincia (verificado con _es_noticia_provincial)
  2. Si no hay ninguno estrictamente provincial, se acepta cualquier nota argentina de esa fuente
  3. Solo 1 artículo por provincia por ejecución

Se excluyen Santiago del Estero (tiene su propio job diario) y las fuentes nacionales.
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
logger = logging.getLogger("federal_diario")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

MIN_CHARS = 250
DEDUP_THRESHOLD = 0.45
DEDUP_HOURS = 20  # ventana más larga: cubre lo de ayer + hoy

# Provincias que tienen su propio job dedicado
_PROVINCIAS_CON_JOB_PROPIO = {"Santiago del Estero"}

# Orden geográfico: sur → norte (narrativa federal)
_ORDEN_GEOGRAFICO = [
    "Tierra del Fuego", "Santa Cruz", "Chubut", "Río Negro", "Neuquén",
    "La Pampa", "Buenos Aires", "CABA", "Entre Ríos", "Corrientes",
    "Misiones", "Santa Fe", "Córdoba", "San Luis", "Mendoza",
    "San Juan", "La Rioja", "Catamarca", "Chaco", "Formosa",
    "Tucumán", "Salta", "Jujuy",
]

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

_ARGENTINA_MENTIONS = (
    "argentina", "buenos aires", "córdoba", "mendoza", "rosario",
    "santiago del estero", "tucumán", "salta", "jujuy", "neuquén",
    "corrientes", "chaco", "misiones", "entre ríos", "santa fe",
    "la pampa", "san juan", "san luis", "río negro", "chubut",
    "santa cruz", "tierra del fuego", "formosa", "catamarca", "la rioja",
    "caba", "capital federal", "patagonia", "noa", "cuyo", "litoral",
    "milei", "kirchner", "massa", "bullrich", "kicillof", "larreta",
    "casa rosada", "oficialismo", "peronismo", "kirchnerismo",
    "congreso nacional", "senado argentino", "diputados argentinos",
    "gobierno argentino", "gobierno nacional", "gobierno de argentina",
    "peso argentino", "pesos argentinos", "dólar blue", "dolar blue",
    "indec", "anses", "afip", "arca", "banco central", "bcra",
    "canasta básica", "cepo cambiario",
    "telam", "conicet", "inta", "inti", "ypf", "aerolíneas",
    "argentino", "argentina", "porteño", "porteña", "bonaerense",
)

_DEMONYMOS = {
    "Buenos Aires": "bonaerenses", "CABA": "porteños",
    "Córdoba": "cordobeses", "Mendoza": "mendocinos",
    "Santa Fe": "santafesinos", "Tucumán": "tucumanos",
    "Salta": "salteños", "Jujuy": "jujeños",
    "Misiones": "misioneros", "Chaco": "chaqueños",
    "Corrientes": "correntinos", "Entre Ríos": "entrerrianos",
    "Formosa": "formoseños", "La Rioja": "riojanos",
    "Catamarca": "catamarqueños", "San Juan": "sanjuaninos",
    "San Luis": "puntanos", "Neuquén": "neuquinos",
    "Río Negro": "rionegrinos", "Chubut": "chubutenses",
    "Santa Cruz": "santacruceños", "Tierra del Fuego": "fueguinos",
    "La Pampa": "pampeanos",
}

_ADJETIVOS = {
    "Buenos Aires": "bonaerense", "CABA": "porteño",
    "Córdoba": "cordobés", "Mendoza": "mendocino",
    "Santa Fe": "santafesino", "Tucumán": "tucumano",
    "Salta": "salteño", "Jujuy": "jujeño",
    "Misiones": "misionero", "Chaco": "chaqueño",
    "Corrientes": "correntino", "Entre Ríos": "entrerriano",
    "Formosa": "formoseño", "La Rioja": "riojano",
    "Catamarca": "catamarqueño", "San Juan": "sanjuanino",
    "San Luis": "puntano", "Neuquén": "neuquino",
    "Río Negro": "rionegrino", "Chubut": "chubutense",
    "Santa Cruz": "santacruceño", "Tierra del Fuego": "fueguino",
    "La Pampa": "pampeano",
}

_categoria_id_cache: dict[str, int] = {}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s if unicodedata.category(c) != "Mn")


def _palabras(titulo: str) -> set:
    s = _norm(titulo)
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return {p for p in s.split() if len(p) > 3 and p not in _STOPWORDS}


def _jaccard(a: str, b: str) -> float:
    wa, wb = _palabras(a), _palabras(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _es_duplicado(titulo: str, recientes: list[str]) -> bool:
    return any(_jaccard(titulo, t) >= DEDUP_THRESHOLD for t in recientes)


def _menciona_argentina(title: str, url: str, summary: str) -> bool:
    combined = _norm(f"{title} {url} {summary}".lower())
    return any(_norm(ref) in combined for ref in _ARGENTINA_MENTIONS)


def _es_noticia_provincial(title: str, url: str, summary: str, provincia: str) -> bool:
    dem = _DEMONYMOS.get(provincia, "")
    adj = _ADJETIVOS.get(provincia, "")
    combined = _norm(f"{title} {url} {summary}".lower())
    checks = [provincia] + ([dem] if dem else []) + ([adj] if adj else [])
    return any(_norm(c.lower()) in combined for c in checks)


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


def _intentar_publicar(entry: dict, source: dict, provincia: str, titulos_recientes: list[str]) -> bool:
    """
    Intenta publicar un artículo. Retorna True si se publicó con éxito.
    """
    url = entry.get("url", "").strip()
    title = entry.get("title", "").strip()
    if not url or len(title) < 10:
        return False

    if database.is_seen(url):
        return False

    summary = entry.get("summary", "")

    if _es_duplicado(title, titulos_recientes):
        logger.info(f"    [DUP] {title[:55]}")
        database.mark_seen(url, title, source["name"])
        return False

    if not _menciona_argentina(title, url, summary):
        logger.info(f"    [AR BLOCK] {title[:55]}")
        database.mark_seen(url, title, source["name"])
        return False

    article = extract_article(url, source)
    if not article:
        return False

    text = article.get("text", "").strip()
    if len(text) < MIN_CHARS:
        logger.info(f"    [CORTO] {len(text)} chars — {title[:50]}")
        database.mark_seen(url, title, source["name"])
        return False

    img_url = article.get("image_url") or entry.get("image_url") or _get_og_image(url)
    if _imagen_es_logo(img_url):
        img_url = None

    img_id = None
    if img_url:
        try:
            img_id = wordpress.upload_image(img_url, title)
        except Exception as e:
            logger.warning(f"    Imagen fallida: {e}")

    # Categoría: nombre de la provincia
    cat_id = _get_categoria_id(provincia)
    categories = [cat_id] if cat_id else []

    body_html = _build_body_html(text, source["name"], url)

    try:
        result = wordpress.create_post(
            title=title,
            content=body_html,
            status="publish",
            featured_media=img_id,
            sticky=False,
            categories=categories,
        )
    except Exception as e:
        logger.error(f"    Error WP: {e}")
        return False

    if not result or not result.get("id"):
        return False

    database.mark_seen(url, title, source["name"])
    titulos_recientes.append(title)
    logger.info(f"    ✓ PUBLICADO [{provincia}] {title[:65]}")
    time.sleep(1)
    return True


def run():
    database.init_db()
    logger.info("=== Barrido federal diario — 1 nota por provincia ===")

    titulos_recientes = database.get_recent_titles(hours=DEDUP_HOURS)
    logger.info(f"Deduplicador: {len(titulos_recientes)} títulos en últimas {DEDUP_HOURS}h")

    # Agrupar fuentes por provincia (excluir SDE y fuentes sin provincia)
    fuentes_por_provincia: dict[str, list[dict]] = {}
    for source in config.NEWS_SOURCES:
        prov = source.get("provincia", "")
        if not prov or prov in _PROVINCIAS_CON_JOB_PROPIO:
            continue
        fuentes_por_provincia.setdefault(prov, []).append(source)

    # Procesar en orden geográfico sur→norte
    provincias_ordenadas = [p for p in _ORDEN_GEOGRAFICO if p in fuentes_por_provincia]
    # Añadir provincias no listadas en el orden geográfico (por si acaso)
    for p in fuentes_por_provincia:
        if p not in provincias_ordenadas:
            provincias_ordenadas.append(p)

    cubierta: set[str] = set()
    sin_cobertura: list[str] = []

    for provincia in provincias_ordenadas:
        fuentes = fuentes_por_provincia[provincia]
        logger.info(f"\n▶ {provincia.upper()} ({', '.join(s['name'] for s in fuentes)})")

        publicado = False

        # Pasada 1: artículos estrictamente provinciales
        for source in fuentes:
            if publicado:
                break
            entries = fetch_entries(source, max_items=source.get("max_articles", 5))
            for entry in entries:
                url = entry.get("url", "")
                title = entry.get("title", "")
                summary = entry.get("summary", "")
                if not _es_noticia_provincial(title, url, summary, provincia):
                    continue  # no es sobre esta provincia → siguiente
                if _intentar_publicar(entry, source, provincia, titulos_recientes):
                    publicado = True
                    cubierta.add(provincia)
                    break

        # Pasada 2 (fallback): cualquier nota argentina de esa fuente
        if not publicado:
            logger.info(f"  [FALLBACK] No hubo nota estrictamente provincial. Aceptando cualquier nota argentina.")
            for source in fuentes:
                if publicado:
                    break
                entries = fetch_entries(source, max_items=source.get("max_articles", 5))
                for entry in entries:
                    if _intentar_publicar(entry, source, provincia, titulos_recientes):
                        publicado = True
                        cubierta.add(provincia)
                        break

        if not publicado:
            sin_cobertura.append(provincia)
            logger.warning(f"  [SIN COBERTURA] {provincia}")

    # Resumen final
    logger.info(f"\n{'═'*60}")
    logger.info(f"COBERTURA FEDERAL — {len(cubierta)}/{len(provincias_ordenadas)} provincias cubiertas")
    if cubierta:
        logger.info(f"  ✓ {', '.join(sorted(cubierta))}")
    if sin_cobertura:
        logger.warning(f"  ✗ Sin nota hoy: {', '.join(sin_cobertura)}")
    logger.info(f"{'═'*60}")


if __name__ == "__main__":
    run()
