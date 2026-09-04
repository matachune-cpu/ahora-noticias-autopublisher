"""
Corrige la nota de Zamora+Malvinas en WordPress:
reemplaza "gobernador" por "senador nacional" en título y cuerpo.
"""
import json
import logging
import os
import re

import requests
from dotenv import load_dotenv

load_dotenv()
import config

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("editar_zamora")

BUSCAR_KEYWORD = "Zamora apoyó a Milei"

TITULO_CORRECTO = (
    "'Ninguna especulación electoral por encima': el senador Zamora apoyó a Milei "
    "en la causa Malvinas y pidió unidad nacional"
)

CUERPO_CORRECTO = """
<p>El senador nacional por Santiago del Estero, Gerardo Zamora, sorprendió este jueves
al respaldar públicamente la cadena nacional del presidente Javier Milei sobre la causa
Malvinas, llamando a la unidad de todos los argentinos por encima de cualquier
diferencia política o electoral.</p>

<p>En un mensaje publicado en sus redes sociales, el referente del Frente Cívico por
Santiago afirmó que "es muy valioso el cambio de posición del Gobierno nacional respecto
a nuestras Islas Malvinas" y que "esto permite que podamos estar todos los argentinos
de acuerdo: las Islas Malvinas nos pertenecen".</p>

<h2>El apoyo a la estrategia diplomática y el bloqueo petrolero</h2>

<p>Zamora manifestó su acuerdo con la decisión de fortalecer la presencia argentina en
la zona del Atlántico Sur y antártica, y con que se lleve adelante "una firme estrategia
diplomática y jurídica internacional, junto a todas las acciones necesarias para ejercer
nuestro derecho".</p>

<p>El senador destacó especialmente un punto de relevancia geopolítica: "Es de suma
importancia que el gobierno nacional haya decidido aplicar con firmeza todas las acciones
al alcance para no permitir la explotación ilegítima de nuestros recursos naturales, y
con ello impedir, por ejemplo, que se avance en la exploración petrolera de una empresa
de Israel, junto a Gran Bretaña".</p>

<h2>El llamado que sorprendió: 'frente institucional y político de todos los argentinos'</h2>

<p>El punto más llamativo del mensaje fue el llamado explícito a la unidad más allá de
las diferencias partidarias: "Estoy absolutamente de acuerdo en que ningún interés
subalterno, diferencia política o especulación electoral puede estar por encima de una
causa sagrada para los intereses de nuestra nación. La causa Malvinas es indudablemente
una de ellas, y por ello debemos estar unidos en un frente institucional y político todos
los argentinos, para defender nuestra soberanía".</p>

<p>El senador cerró su mensaje con la frase: "Las Malvinas son Argentinas!!!"</p>

<h2>El contexto: la cadena nacional de Milei</h2>

<p>Las palabras de Zamora llegaron en respuesta a una alocución presidencial de Milei en
cadena nacional, en la que el mandatario nacional anunció una postura firme sobre la
soberanía argentina de las Islas Malvinas e impulsó medidas para bloquear la exploración
petrolera de empresas extranjeras en aguas que Argentina reclama como propias.</p>

<p>El respaldo de Zamora —uno de los referentes históricos del peronismo santiagueño—
fue recibido con sorpresa en la escena política nacional y refuerza la idea de que la
causa Malvinas genera consenso transversal por encima de las diferencias partidarias.</p>

<p><em>Fuente: redes sociales / Gobierno de Santiago del Estero</em></p>
"""


def _auth_header() -> dict:
    user = os.getenv("WP_USERNAME", "")
    pwd = os.getenv("WP_APP_PASSWORD", "")
    import base64
    token = base64.b64encode(f"{user}:{pwd}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


def main():
    base = os.getenv("WP_URL", "").rstrip("/")
    if not base:
        logger.error("WP_URL no configurado.")
        return

    # 1. Buscar el post por keyword
    search_url = f"{base}/wp-json/wp/v2/posts"
    params = {"search": BUSCAR_KEYWORD, "per_page": 5, "status": "publish"}
    resp = requests.get(search_url, params=params, headers=_auth_header(), timeout=20)
    resp.raise_for_status()
    posts = resp.json()

    if not posts:
        logger.error(f"No se encontró ningún post con keyword '{BUSCAR_KEYWORD}'.")
        return

    # Tomar el más reciente que coincida
    post = posts[0]
    post_id = post["id"]
    post_title = post.get("title", {}).get("rendered", "")
    post_link = post.get("link", "")
    logger.info(f"Post encontrado: ID={post_id} | {post_title[:70]}")
    logger.info(f"  URL: {post_link}")

    # 2. Actualizar título y contenido
    update_url = f"{base}/wp-json/wp/v2/posts/{post_id}"
    payload = {
        "title": TITULO_CORRECTO,
        "content": CUERPO_CORRECTO,
    }
    patch = requests.post(
        update_url,
        data=json.dumps(payload),
        headers={**_auth_header(), "Content-Type": "application/json"},
        timeout=30,
    )
    patch.raise_for_status()
    updated = patch.json()
    logger.info(f"✓ Post actualizado: ID={updated.get('id')} | {updated.get('link', '')}")
    logger.info(f"  Nuevo título: {updated.get('title', {}).get('rendered', '')[:80]}")


if __name__ == "__main__":
    main()
