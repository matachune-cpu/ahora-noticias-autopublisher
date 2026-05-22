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
    """Obtiene entradas de noticias via RSS o scraping de portada según configuración."""
    if source.get("rss"):
        return _fetch_rss(source, max_items)
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


def extract_article(url: str, source_name: str, title: str, summary: str) -> Optional[Article]:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "lxml")

        # Remove nav, ads, footers
        for tag in soup(["nav", "footer", "script", "style", "aside", "iframe"]):
            tag.decompose()

        # Extract main article text
        full_text = _extract_text(soup)

        # Verificar que el artículo tiene contenido real
        texto_util = (full_text or "").strip()
        if len(texto_util) < MIN_ARTICLE_CHARS:
            # Si el texto es muy corto, intentar con el summary
            if len((summary or "").strip()) >= MIN_ARTICLE_CHARS:
                texto_util = summary
            else:
                logger.warning(
                    f"Articulo descartado por contenido insuficiente "
                    f"({len(texto_util)} chars < {MIN_ARTICLE_CHARS}): {url}"
                )
                return None

        # Extract first article image
        image_url = _extract_image(soup, url)

        return Article(
            url=url,
            title=title,
            summary=summary,
            full_text=texto_util,
            source_name=source_name,
            image_url=image_url,
        )
    except Exception as e:
        logger.error(f"Scrape error for {url}: {e}")
        return None


def _clean_p(p) -> str:
    """
    Extrae el texto de un <p> con separadores de espacio entre elementos inline
    (evita que <strong>texto</strong>siguiente quede como 'textosiguiente').
    Normaliza espacios múltiples que puede dejar BeautifulSoup.
    """
    import re
    raw = p.get_text(separator=" ", strip=True)
    return re.sub(r" {2,}", " ", raw).strip()


def _extract_text(soup: BeautifulSoup) -> str:
    # Try common article containers in order of specificity
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

    # Fallback: all paragraphs
    paragraphs = soup.find_all("p")
    return "\n".join(_clean_p(p) for p in paragraphs if len(_clean_p(p)) > 40)


def _extract_image(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    # Try Open Graph image first
    og_img = soup.find("meta", property="og:image")
    if og_img and og_img.get("content"):
        return og_img["content"]

    # Try first large img in article
    for img in soup.find_all("img"):
        src = img.get("src", "")
        if src and any(ext in src.lower() for ext in [".jpg", ".jpeg", ".png", ".webp"]):
            if src.startswith("http"):
                return src
    return None
