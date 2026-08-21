"""
Descubre el meta key que usa el checkbox 'Mostrar en el hero de la portada'.
Busca posts que tengan ese campo activado y muestra todos sus meta fields.
Uso: python _diagnosticar_meta_hero.py
"""
import requests
import base64
import json
from dotenv import load_dotenv

load_dotenv()
import config


def _auth_header():
    credentials = f"{config.WP_USERNAME}:{config.WP_APP_PASSWORD}"
    token = base64.b64encode(credentials.encode()).decode()
    return {"Authorization": f"Basic {token}"}


def descubrir_meta_hero():
    base = f"{config.WP_URL}/wp-json/wp/v2"
    headers = _auth_header()

    # 1. Ver qué meta fields están registrados en la API
    print("\n=== Meta fields registrados en la API REST ===")
    schema = requests.get(f"{base}/posts", headers=headers, params={"context": "edit", "_fields": "meta"}, timeout=15)
    if schema.ok:
        posts = schema.json()
        if posts:
            meta = posts[0].get("meta", {})
            print(f"Meta fields visibles en API: {list(meta.keys())}")
            for k, v in meta.items():
                print(f"  {k!r}: {v!r}")
        else:
            print("No hay posts o meta fields no expuestos en la API pública.")
    else:
        print(f"Error: {schema.status_code}")

    # 2. Buscar sticky posts (nuestros) y ver si tienen meta de hero
    print("\n=== Posts sticky actuales y su meta ===")
    sticky = requests.get(f"{base}/posts", headers=headers,
                          params={"sticky": True, "per_page": 5, "context": "edit"}, timeout=15)
    if sticky.ok:
        for p in sticky.json():
            print(f"\nPost ID={p['id']} sticky={p.get('sticky')} título={p.get('title',{}).get('rendered','')[:60]}")
            print(f"  Meta: {p.get('meta', {})}")
    else:
        print(f"Error: {sticky.status_code}")

    # 3. Buscar el endpoint de tipos de post custom
    print("\n=== Endpoints disponibles en la API ===")
    root = requests.get(f"{config.WP_URL}/wp-json/", headers=headers, timeout=15)
    if root.ok:
        data = root.json()
        namespaces = data.get("namespaces", [])
        print(f"Namespaces: {namespaces}")

    # 4. Intentar buscar via WP Query custom (post__in con meta_query no disponible en REST)
    # En su lugar, buscar los 5 posts más recientes con context=edit para ver todos los campos
    print("\n=== Últimos 5 posts con todos los campos (context=edit) ===")
    recientes = requests.get(f"{base}/posts", headers=headers,
                             params={"per_page": 5, "context": "edit", "orderby": "date", "order": "desc"},
                             timeout=15)
    if recientes.ok:
        for p in recientes.json():
            pid = p["id"]
            titulo = p.get("title", {}).get("rendered", "")[:50]
            meta = p.get("meta", {})
            sticky = p.get("sticky", False)
            print(f"\n  ID={pid} sticky={sticky} | {titulo}")
            if meta:
                print(f"  Meta: {json.dumps(meta, ensure_ascii=False)}")
            else:
                print(f"  Meta: (vacío o no expuesto)")


if __name__ == "__main__":
    descubrir_meta_hero()
