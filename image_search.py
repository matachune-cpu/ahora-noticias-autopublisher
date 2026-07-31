"""
Búsqueda de imágenes ilustrativas en Google Custom Search API.
Se usa como fallback cuando el artículo no tiene imagen propia o la imagen
fue descartada por contener marca de agua de una agencia de noticias.

Requiere en .env:
    GOOGLE_SEARCH_API_KEY  → clave de Google Cloud (APIs & Services)
    GOOGLE_SEARCH_CX       → ID del Programmable Search Engine (cx)

Cómo obtener las credenciales:
    1. Ir a https://programmablesearchengine.google.com/ y crear un motor de
       búsqueda configurado para buscar en toda la web con imágenes activadas.
    2. Copiar el "Search engine ID" como GOOGLE_SEARCH_CX.
    3. Ir a https://console.cloud.google.com/ → Credenciales → API Key y
       habilitar "Custom Search API" para esa clave.
"""
import requests
import logging
import config

logger = logging.getLogger(__name__)

SEARCH_URL = "https://www.googleapis.com/customsearch/v1"

# Extensiones de imagen aceptadas
_IMG_EXTS = (".jpg", ".jpeg", ".png", ".webp")


def search_image(query: str) -> str | None:
    """
    Busca una imagen ilustrativa en Google para el query dado.
    Filtra solo imágenes con licencia de uso libre y extensión válida.
    Retorna la URL de la primera imagen adecuada, o None si falla.
    """
    if not config.GOOGLE_SEARCH_API_KEY or not config.GOOGLE_SEARCH_CX:
        logger.debug(
            "Google Image Search no configurado "
            "(faltan GOOGLE_SEARCH_API_KEY o GOOGLE_SEARCH_CX en .env)"
        )
        return None

    try:
        r = requests.get(
            SEARCH_URL,
            params={
                "key": config.GOOGLE_SEARCH_API_KEY,
                "cx": config.GOOGLE_SEARCH_CX,
                "q": query,
                "searchType": "image",
                "num": 5,
                "imgType": "photo",
                "safe": "active",
                "imgSize": "large",
                "rights": "cc_publicdomain|cc_attribute|cc_sharealike",
            },
            timeout=15,
        )
        r.raise_for_status()
        items = r.json().get("items", [])

        for item in items:
            img_url = item.get("link", "")
            if img_url.startswith("http") and img_url.lower().endswith(_IMG_EXTS):
                logger.info(
                    f"Google Image Search: imagen encontrada para "
                    f"'{query[:60]}' → {img_url[:100]}"
                )
                return img_url

        logger.warning(f"Google Image Search: sin resultados para '{query[:60]}'")

    except requests.HTTPError as e:
        body = e.response.text if e.response else ""
        logger.warning(f"Google Image Search HTTP error (no fatal): {e} | {body[:200]}")
    except Exception as e:
        logger.warning(f"Google Image Search error (no fatal): {e}")

    return None
