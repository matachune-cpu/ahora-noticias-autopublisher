"""
Búsqueda de imágenes ilustrativas en Google Custom Search API.
Se usa como fallback cuando el artículo no tiene imagen propia o la imagen
fue descartada por contener marca de agua de una agencia de noticias.

Requiere en .env:
    GOOGLE_SEARCH_API_KEY  → clave de Google Cloud (APIs & Services)
    GOOGLE_SEARCH_CX       → ID del Programmable Search Engine (cx)
"""
import re
import requests
import logging
import unicodedata
import config

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")

# Dimensiones mínimas para imagen de portada en redes sociales (1200×630 OG)
_MIN_WIDTH = 1200
_MIN_HEIGHT = 600

# Dominios de medios de noticias y agencias — suelen ser logos o fotos con marca de agua
_NEWS_DOMAINS = {
    "infobae.com", "lanacion.com.ar", "clarin.com", "pagina12.com.ar",
    "telam.com.ar", "reuters.com", "apimages.com", "gettyimages.com",
    "ap.org", "agenciafe.com", "ambito.com", "cronista.com",
    "iprofesional.com", "perfil.com", "tn.com.ar", "minutouno.com",
    "cadena3.com", "elliberal.com.ar", "nuevodiarioweb.com.ar",
}

# Palabras en URLs que sugieren logo/marca
_LOGO_URL_TOKENS = {"logo", "logos", "brand", "logotipo", "icon", "favicon", "watermark"}

_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "en", "con", "por", "para", "que",
    "se", "lo", "le", "les", "su", "sus", "y", "o", "a", "e",
    "es", "son", "fue", "era", "ha", "han", "hay", "no", "ni",
    "si", "ya", "mas", "pero", "como", "muy", "bien",
    "cuando", "donde", "quien", "cual", "sobre", "ante",
    "tras", "entre", "durante", "desde", "hasta", "tambien",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "todo", "toda", "todos", "todas", "otro", "otra",
    "mismo", "misma", "cada", "nuevo", "nueva", "gran", "solo",
    "segun", "junto", "luego", "pese",
}


def _build_query(title: str) -> str:
    """
    Extrae palabras clave del título para construir una query de búsqueda de imagen
    más precisa: sin stopwords, sin signos de puntuación, máximo 6 palabras.
    """
    sin_tildes = unicodedata.normalize("NFD", title)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    limpio = re.sub(r"[^\w\s]", " ", sin_tildes.lower())
    palabras = [p for p in limpio.split() if len(p) > 3 and p not in _STOPWORDS_ES]
    query = " ".join(palabras[:6])
    return query or title[:80]


def _url_parece_logo(url: str) -> bool:
    """Descarta imágenes cuya URL sugiere que es un logo o ícono."""
    url_lower = url.lower()
    return any(token in url_lower for token in _LOGO_URL_TOKENS)


def _dominio_es_medio(url: str) -> bool:
    """Descarta imágenes que provienen de dominios de medios de noticias."""
    try:
        from urllib.parse import urlparse
        host = urlparse(url).netloc.lower().lstrip("www.")
        return any(host == d or host.endswith("." + d) for d in _NEWS_DOMAINS)
    except Exception:
        return False


def _cumple_dimensiones(item: dict) -> bool:
    """
    Verifica que la imagen supera el mínimo de 1200×600 px.
    La API de Google devuelve image.width / image.height cuando están disponibles.
    Si no están, deja pasar (no bloquear por falta de dato).
    """
    img_meta = item.get("image", {})
    w = img_meta.get("width")
    h = img_meta.get("height")
    if w and h:
        return int(w) >= _MIN_WIDTH and int(h) >= _MIN_HEIGHT
    return True  # sin datos de dimensión, deja pasar


def search_image(query: str) -> str | None:
    """
    Busca una imagen ilustrativa en Google para el título/query dado.
    - Construye una query con las palabras clave del título.
    - Pide 10 resultados xlarge para maximizar chances de una foto grande.
    - Descarta imágenes con URL sospechosa de logo o de dominio de medio de noticias.
    - Filtra por dimensiones mínimas 1200×600 cuando la API reporta el tamaño.
    - No filtra por licencia (rights) para maximizar resultados disponibles.
    Retorna la URL de la primera imagen adecuada, o None si falla.
    """
    if not config.GOOGLE_SEARCH_API_KEY or not config.GOOGLE_SEARCH_CX:
        logger.debug(
            "Google Image Search no configurado "
            "(faltan GOOGLE_SEARCH_API_KEY o GOOGLE_SEARCH_CX en .env)"
        )
        return None

    smart_query = _build_query(query)
    logger.info(f"Google Image Search: query='{smart_query}' (original='{query[:60]}')") 

    try:
        r = requests.get(
            SEARCH_URL,
            params={
                "key": config.GOOGLE_SEARCH_API_KEY,
                "cx": config.GOOGLE_SEARCH_CX,
                "q": smart_query,
                "searchType": "image",
                "num": 10,
                "imgType": "photo",
                "safe": "active",
                "imgSize": "xlarge",
            },
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("items", [])

        for item in items:
            img_url = item.get("link", "")

            if not img_url.startswith("http"):
                continue
            if not img_url.lower().endswith(_IMG_EXTS):
                continue
            if _url_parece_logo(img_url):
                logger.debug(f"  [IMG] Descartada por URL de logo: {img_url[:80]}")
                continue
            if _dominio_es_medio(img_url):
                logger.debug(f"  [IMG] Descartada por dominio de medio: {img_url[:80]}")
                continue
            if not _cumple_dimensiones(item):
                logger.debug(f"  [IMG] Descartada por dimensiones insuficientes: {img_url[:80]}")
                continue

            logger.info(f"  → Imagen encontrada: {img_url[:100]}")
            return img_url

        logger.warning(f"Google Image Search: sin resultados válidos para '{smart_query}'")

    except requests.HTTPError as e:
        body = e.response.text if e.response else ""
        logger.warning(f"Google Image Search HTTP error (no fatal): {e} | {body[:200]}")
    except Exception as e:
        logger.warning(f"Google Image Search error (no fatal): {e}")

    return None
