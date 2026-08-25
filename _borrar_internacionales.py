"""
Busca y elimina posts publicados recientemente que NO sean de Argentina.
Solo actúa sobre categorías que deben ser 100% argentinas.
Categorías internacionales permitidas: Espectáculos, Tecnología.

Uso:
    python _borrar_internacionales.py [--horas 3] [--dry-run]
"""
import argparse
import base64
import logging
import unicodedata
from datetime import datetime, timezone, timedelta

import requests
from dotenv import load_dotenv

load_dotenv()
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("borrar_internacionales")

# Mismo set que _publicar_sin_ia.py
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
    "poder ejecutivo", "poder judicial argentino",
    "peso argentino", "pesos argentinos", "dólar blue", "dolar blue",
    "indec", "anses", "afip", "arca", "banco central", "bcra",
    "canasta básica", "cepo cambiario", "tipo de cambio argentino",
    "telam", "conicet", "inta", "inti", "ypf", "aerolíneas",
    "infobae", "clarin", "la nacion", "pagina 12",
    "argentino", "argentina", "porteño", "porteña", "bonaerense",
)

# Categorías donde se tolera contenido internacional
_CATEGORIAS_INTL_OK = {"Espectáculos", "Tecnología"}


def _auth_header() -> dict:
    creds = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    token = base64.b64encode(creds.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def _menciona_argentina(title: str, content: str) -> bool:
    combined = f"{title} {content}".lower()
    s = unicodedata.normalize("NFD", combined)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    for ref in _ARGENTINA_MENTIONS:
        ref_n = "".join(
            c for c in unicodedata.normalize("NFD", ref)
            if unicodedata.category(c) != "Mn"
        )
        if ref_n in s:
            return True
    return False


def _get_category_names() -> dict[int, str]:
    """Obtiene el mapa {id: nombre} de todas las categorías WP."""
    url = f"{config.WP_URL}/wp-json/wp/v2/categories"
    cats = {}
    page = 1
    while True:
        resp = requests.get(url, params={"per_page": 100, "page": page}, timeout=15)
        if resp.status_code != 200:
            break
        batch = resp.json()
        if not batch:
            break
        for c in batch:
            cats[c["id"]] = c["name"]
        if len(batch) < 100:
            break
        page += 1
    return cats


def main(horas: int = 3, dry_run: bool = False):
    after = (datetime.now(timezone.utc) - timedelta(hours=horas)).isoformat()
    logger.info(f"Buscando posts publicados desde {after} (últimas {horas}h)...")

    cat_names = _get_category_names()
    logger.info(f"Categorías WP cargadas: {len(cat_names)}")

    base_url = f"{config.WP_URL}/wp-json/wp/v2/posts"
    headers = _auth_header()
    page = 1
    eliminados = 0
    revisados = 0

    while True:
        params = {
            "after": after,
            "per_page": 50,
            "page": page,
            "status": "publish",
            "_fields": "id,title,content,categories,link",
        }
        resp = requests.get(base_url, headers=headers, params=params, timeout=20)
        if resp.status_code != 200:
            logger.error(f"Error consultando posts: {resp.status_code}")
            break
        posts = resp.json()
        if not posts:
            break

        for post in posts:
            revisados += 1
            pid = post["id"]
            title = post.get("title", {}).get("rendered", "")
            content_raw = post.get("content", {}).get("rendered", "")
            # Limpiar HTML del contenido
            import re
            content = re.sub(r"<[^>]+>", " ", content_raw)
            link = post.get("link", "")
            cat_ids = post.get("categories", [])
            cat_nombre_list = [cat_names.get(cid, "") for cid in cat_ids]
            cat_nombres = set(cat_nombre_list)

            # Si la categoría permite internacional → saltar
            if cat_nombres & _CATEGORIAS_INTL_OK:
                continue

            # Si menciona Argentina → saltar
            if _menciona_argentina(title, content):
                continue

            # No menciona Argentina y no está en categoría permitida → eliminar
            logger.info(
                f"  [INTL] Eliminando ID={pid} [{', '.join(cat_nombres)}] {title[:70]}"
            )
            logger.info(f"         {link}")

            if not dry_run:
                del_resp = requests.delete(
                    f"{config.WP_URL}/wp-json/wp/v2/posts/{pid}",
                    headers=headers,
                    params={"force": True},
                    timeout=15,
                )
                if del_resp.status_code in (200, 204):
                    logger.info(f"  ✓ Eliminado ID={pid}")
                    eliminados += 1
                else:
                    logger.error(f"  ✗ Error {del_resp.status_code}: {del_resp.text[:150]}")
            else:
                eliminados += 1

        if len(posts) < 50:
            break
        page += 1

    suffix = " (DRY RUN)" if dry_run else ""
    logger.info(f"\nRevisados: {revisados} | Eliminados{suffix}: {eliminados}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--horas", type=int, default=3,
                        help="Ventana de tiempo en horas hacia atrás (default: 3)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Solo muestra qué se eliminaría, sin borrar")
    args = parser.parse_args()
    main(horas=args.horas, dry_run=args.dry_run)
