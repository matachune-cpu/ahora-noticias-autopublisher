import re
import feedparser
import requests
from bs4 import BeautifulSoup
from dataclasses import dataclass
from typing import Optional
import logging

logger = logging.getLogger(__name__)

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}


@dataclass
class Article:
    url: str
    title: str
    summary: str
    full_text: str
    source_name: str
    image_url: Optional[str] = None


def fetch_entries(source: dict, max_items: int = 10) -> list[dict]:
    """Obtiene entradas según el tipo de fuente configurado."""
    if source.get("rss"):
        return _fetch_rss(source, max_items)
    elif source.get("labanda_api"):
        return _fetch_labanda_api(source, max_items)
    elif source.get("santiago_ciudad"):
        return _fetch_santiago_ciudad(source, max_items)
    elif source.get("scrape_links"):
        return _fetch_by_scraping(source, max_items)
    return []


def _fetch_rss(source: dict, max_items: int) -> list[dict]:
    try:
        feed = feedparser.parse(source["rss"])
        entries = []
        for entry in feed.entries[:max_items]:
            entries.append({
                "url": entry.get("link", ""),
                "title": entry.get("title", ""),
                "summary": entry.get("summary", ""),
            })
        return entries
    except Exception as e:
        logger.error(f"RSS error for {source['name']}: {e}")
        return []


def _fetch_labanda_api(source: dict, max_items: int) -> list[dict]:
    """
    Consume la API JSON de la Municipalidad de La Banda.
    El contenido completo y la imagen ya vienen en la respuesta,
    por lo que no es necesario scrapear artículos individuales.
    """
    try:
        resp = requests.get(source["labanda_api"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        noticias = resp.json().get("noticias", [])

        entries = []
        for n in noticias[:max_items]:
            art_id = n.get("_id", "")
            if not art_id:
                continue

            url = f"https://labanda.gob.ar/noticias/{art_id}"
            title = n.get("title", "").strip()
            if not title:
                continue

            # Limpiar HTML del contenido
            content_html = n.get("content", "") or n.get("excerpt", "")
            soup = BeautifulSoup(content_html, "lxml")
            full_text = re.sub(r"\s+", " ", soup.get_text(separator=" ", strip=True))

            # Imagen desde Cloudinary
            image_url = None
            img_data = n.get("image")
            if isinstance(img_data, dict):
                image_url = img_data.get("url")

            entries.append({
                "url": url,
                "title": title,
                "summary": n.get("excerpt", ""),
                "full_text": full_text,    # ya disponible, no hay que scrapear
                "image_url": image_url,
            })

        logger.info(f"La Banda API: {len(entries)} noticias obtenidas")
        return entries
    except Exception as e:
        logger.error(f"La Banda API error: {e}")
        return []


def _fetch_santiago_ciudad(source: dict, max_items: int) -> list[dict]:
    """
    Scrapea el listado de noticias de santiagociudad.gov.ar.
    Extrae IDs y slugs para construir las URLs de cada artículo.
    """
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        links = soup.select("a[href*='/noticias/']")
        seen = set()
        entries = []
        for link in links:
            href = link.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = "https://www.santiagociudad.gov.ar" + href
            if href in seen or "/noticias/" not in href:
                continue
            # Solo links de artículos individuales (tienen ID numérico)
            if not re.search(r"/noticias/\d+", href):
                continue
            seen.add(href)
            title = link.get_text(strip=True)
            if len(title) < 10:
                # Buscar título en elemento padre
                parent = link.find_parent(["article", "div", "li"])
                if parent:
                    h = parent.find(["h1", "h2", "h3", "h4", "h5", "h6"])
                    if h:
                        title = h.get_text(strip=True)
            if len(title) < 10:
                continue
            entries.append({"url": href, "title": title, "summary": ""})
            if len(entries) >= max_items:
                break

        logger.info(f"Santiago Ciudad scraping: {len(entries)} artículos encontrados")
        return entries
    except Exception as e:
        logger.error(f"Santiago Ciudad scraping error: {e}")
        return []


def _fetch_by_scraping(source: dict, max_items: int) -> list[dict]:
    """Scrapea la portada del diario para obtener links de artículos recientes."""
    try:
        resp = requests.get(source["url"], headers=HEADERS, timeout=15)
        resp.raise_for_status()
        resp.encoding = resp.apparent_encoding or "utf-8"
        soup = BeautifulSoup(resp.text, "lxml")

        selector = source.get("article_selector", "article a")
        links = soup.select(selector)

        seen = set()
        entries = []
        for link in links:
            href = link.get("href", "")
            if not href:
                continue
            if not href.startswith("http"):
                href = source["url"].rstrip("/") + "/" + href.lstrip("/")
            if href in seen:
                continue
            seen.add(href)
            title = link.get_text(strip=True) or link.get("title", "")
            if len(title) < 15:
                continue
            entries.append({"url": href, "title": title, "summary": ""})
            if len(entries) >= max_items:
                break

        logger.info(f"Scraping {source['name']}: {len(entries)} artículos encontrados")
        return entries
    except Exception as e:
        logger.error(f"Scraping error for {source['name']}: {e}")
        return []


# Mantener compatibilidad con código anterior
def fetch_rss_entries(source: dict, max_items: int = 10) -> list[dict]:
    return fetch_entries(source, max_items)


MIN_ARTICLE_CHARS = 400   # texto mínimo para considerar un artículo completo


def extract_article(url: str, source_name: str, title: str, summary: str,
                    full_text: str = None, image_url: str = None) -> Optional[Article]:
    """
    Extrae el artículo completo.
    Si full_text e image_url ya vienen dados (ej: La Banda API),
    los usa directamente sin hacer scraping adicional.
    """
    # Usar datos pre-cargados si están disponibles (evita request extra)
    if full_text and len(full_text.strip()) >= MIN_ARTICLE_CHARS:
        return Article(
            url=url, title=title, summary=summary,
            full_text=full_text.strip(),
            source_name=source_name, image_url=image_url,
        )

    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove nav, ads, footers
        for tag in soup(["nav", "footer", "script", "style", "aside", "iframe"]):
            tag.decompose()

        # Extract main article text
        texto_util = _extract_text(soup).strip()

        if len(texto_util) < MIN_ARTICLE_CHARS:
            if len((summary or "").strip()) >= MIN_ARTICLE_CHARS:
                texto_util = summary
            else:
                logger.warning(
                    f"Articulo descartado por contenido insuficiente "
                    f"({len(texto_util)} chars < {MIN_ARTICLE_CHARS}): {url}"
                )
                return None

        extracted_image = image_url or _extract_image(soup, url)

        return Article(
            url=url, title=title, summary=summary,
            full_text=texto_util, source_name=source_name,
            image_url=extracted_image,
        )
    except Exception as e:
        logger.error(f"Scrape error for {url}: {e}")
        return None


def _clean_p(p) -> str:
    raw = p.get_text(separator=" ", strip=True)
    return re.sub(r" {2,}", " ", raw).strip()


def _extract_text(soup: BeautifulSoup) -> str:
    selectors = [
        "article",
        '[class*="article-body"]',
        '[class*="nota-cuerpo"]',
        '[class*="content-text"]',
        '[class*="article-content"]',
        "main",
    ]
    for selector in selectors:
        container = soup.select_one(selector)
        if container:
            paragraphs = container.find_all("p")
            parts = [_clean_p(p) for p in paragraphs if len(_clean_p(p)) > 40]
            text = "\n".join(parts)
            if len(text) > 200:
                return text

    paragraphs = soup.find_all("p")
    return "\n".join(_clean_p(p) for p in paragraphs if len(_clean_p(p)) > 40)


def _extract_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        return og_img["content"]

    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            if src.startswith("http"):
                return src
    return None
