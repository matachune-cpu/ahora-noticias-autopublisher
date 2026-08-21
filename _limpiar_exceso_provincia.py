"""
Elimina artículos duplicados por provincia: deja solo el más reciente por categoría-provincia.
Uso: python _limpiar_exceso_provincia.py --provincia "Chaco" --max-keep 1
"""
import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

from publishers import wordpress

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("limpiar_exceso")


def limpiar_provincia(provincia: str, max_keep: int = 1):
    logger.info(f"=== Limpieza de exceso: provincia '{provincia}', conservar {max_keep} ===")

    cat_id = wordpress.get_or_create_category(provincia)
    if not cat_id:
        logger.error(f"No se encontró categoría '{provincia}'")
        return

    posts = wordpress.get_posts_by_category(cat_id, per_page=50)
    logger.info(f"Posts encontrados en categoría '{provincia}': {len(posts)}")

    if len(posts) <= max_keep:
        logger.info("No hay exceso, nada que eliminar.")
        return

    a_eliminar = posts[max_keep:]
    logger.info(f"Eliminando {len(a_eliminar)} post(s) en exceso...")

    for post in a_eliminar:
        pid = post["id"]
        title = post.get("title", {}).get("rendered", "")[:60]
        if wordpress.delete_post(pid):
            logger.info(f"  ✓ Eliminado ID={pid}: {title}")
        else:
            logger.warning(f"  ✗ No se pudo eliminar ID={pid}: {title}")

    logger.info("=== Limpieza completada ===")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--provincia", required=True, help="Nombre de la provincia a limpiar")
    parser.add_argument("--max-keep", type=int, default=1, help="Artículos a conservar (default: 1)")
    args = parser.parse_args()
    limpiar_provincia(args.provincia, args.max_keep)
