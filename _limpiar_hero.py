"""
Limpia el hero: quita stickies viejos y deja solo los max_sticky más recientes.
Uso: python _limpiar_hero.py [--max 4]
"""
import argparse
import logging
from dotenv import load_dotenv

load_dotenv()

from publishers import wordpress

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("limpiar_hero")


def main(max_sticky: int = 4):
    current = wordpress.get_sticky_post_ids()
    logger.info(f"Sticky posts actuales: {len(current)} → {current}")

    if not current:
        logger.info("No hay sticky posts. Nada que hacer.")
        return

    sorted_ids = sorted(current, reverse=True)  # más reciente primero
    to_keep = sorted_ids[:max_sticky]
    to_remove = sorted_ids[max_sticky:]

    logger.info(f"Mantener (más recientes): {to_keep}")
    logger.info(f"Quitar sticky: {to_remove}")

    for pid in to_remove:
        ok = wordpress.set_sticky(pid, False)
        logger.info(f"  {'✓' if ok else '✗'} Sticky quitado a ID={pid}")

    logger.info(f"\nHero actualizado: {len(to_keep)} post(s) destacados")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=4)
    args = parser.parse_args()
    main(max_sticky=args.max)
