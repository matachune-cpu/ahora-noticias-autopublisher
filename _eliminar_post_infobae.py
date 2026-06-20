"""
Script de emergencia: elimina posts de Facebook e Instagram que contengan
el logo de Infobae u otra imagen incorrecta.

Uso:
    # Ver los últimos 20 posts publicados (con sus IDs de FB e IG)
    python _eliminar_post_infobae.py --listar

    # Eliminar por ID de Facebook
    python _eliminar_post_infobae.py --fb-id 123456789_987654321

    # Eliminar por ID de Instagram
    python _eliminar_post_infobae.py --ig-id 18012345678901234

    # Eliminar ambos a la vez
    python _eliminar_post_infobae.py --fb-id 123456789_987654321 --ig-id 18012345678901234

    # Eliminar el último post publicado de fuente Infobae
    python _eliminar_post_infobae.py --ultimo-infobae
"""
import argparse
import sqlite3
import logging
import sys
import os

from dotenv import load_dotenv
load_dotenv()

from publishers import facebook, instagram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("eliminar_post")

DB_PATH = "published_articles.db"


def listar_recientes(n: int = 20):
    if not os.path.exists(DB_PATH):
        print("No se encontró la base de datos.")
        return
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT id, title, source, published_at, fb_post_id, ig_post_id FROM articles ORDER BY id DESC LIMIT ?",
            (n,),
        ).fetchall()
    if not rows:
        print("No hay artículos en la base de datos.")
        return
    print(f"\n{'ID':>5}  {'Fuente':<20} {'Fecha':<20} {'FB ID':<30} {'IG ID':<25} Título")
    print("─" * 140)
    for r in rows:
        fb = r["fb_post_id"] or "—"
        ig = r["ig_post_id"] or "—"
        pub = (r["published_at"] or "")[:19]
        titulo = (r["title"] or "")[:60]
        print(f"{r['id']:>5}  {r['source']:<20} {pub:<20} {fb:<30} {ig:<25} {titulo}")
    print()


def get_ultimo_infobae() -> dict | None:
    if not os.path.exists(DB_PATH):
        return None
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT title, source, published_at, fb_post_id, ig_post_id FROM articles WHERE source = 'Infobae' AND (fb_post_id IS NOT NULL OR ig_post_id IS NOT NULL) ORDER BY id DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def eliminar(fb_id: str | None, ig_id: str | None):
    if not fb_id and not ig_id:
        logger.error("Debes indicar al menos un ID (--fb-id o --ig-id).")
        sys.exit(1)
    if fb_id:
        print(f"Eliminando de Facebook: {fb_id}")
        ok = facebook.delete_post(fb_id)
        print(f"  → {'Eliminado' if ok else 'Error (ver log)'}")
    if ig_id:
        print(f"Eliminando de Instagram: {ig_id}")
        ok = instagram.delete_post(ig_id)
        print(f"  → {'Eliminado' if ok else 'Error (ver log)'}")


def main():
    parser = argparse.ArgumentParser(description="Eliminar posts de FB/IG con imagen incorrecta.")
    parser.add_argument("--listar", action="store_true")
    parser.add_argument("--fb-id", metavar="POST_ID")
    parser.add_argument("--ig-id", metavar="MEDIA_ID")
    parser.add_argument("--ultimo-infobae", action="store_true")
    args = parser.parse_args()

    if args.listar:
        listar_recientes()
        return
    if args.ultimo_infobae:
        post = get_ultimo_infobae()
        if not post:
            print("No se encontró ningún post de Infobae con FB/IG ID.")
            sys.exit(1)
        print(f"Título: {post['title']}")
        print(f"FB ID:  {post['fb_post_id'] or '—'}")
        print(f"IG ID:  {post['ig_post_id'] or '—'}")
        confirmar = input("¿Confirmar eliminación? (s/n): ").strip().lower()
        if confirmar != "s":
            print("Cancelado.")
            return
        eliminar(post["fb_post_id"], post["ig_post_id"])
        return
    if args.fb_id or args.ig_id:
        eliminar(args.fb_id, args.ig_id)
        return
    parser.print_help()


if __name__ == "__main__":
    main()
