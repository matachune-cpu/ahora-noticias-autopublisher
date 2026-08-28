"""
Publicación manual de la nota sobre Eduardo "El Polaco" Groh Riemersma.
Compila información de El Liberal, Nuevo Diario y Diario Panorama.
Publica en WordPress con sticky activado y categoría Santiago del Estero.
"""
import base64
import logging
import time
from datetime import datetime

import requests
from dotenv import load_dotenv

load_dotenv()

import config
import database
from publishers import wordpress

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("publicar_polaco")

# ── DATOS DE LA NOTA ────────────────────────────────────────────────────────

TITULO = (
    "El hombre que salvó a más de 400 perros murió intentando no atropellar a uno"
)

COPY_REDES = (
    "Vivió para salvarlos. 'El Polaco' Riemersma, referente del proteccionismo "
    "animal en Santiago del Estero y fundador del refugio El Montecito de los "
    "Canichones, murió el jueves al esquivar a un perro que cruzó su camino. "
    "Tenía 49 años y más de 400 perros bajo su cuidado."
)

CUERPO_HTML = """
<p>Santiago del Estero despidió este jueves a Eduardo Groh Riemersma, conocido
en toda la provincia como <strong>"El Polaco"</strong>: el hombre que dedicó su
vida entera a rescatar perros en situación de calle y que falleció, con 49 años,
en circunstancias que conmovieron hasta las lágrimas a quienes lo conocían.</p>

<p>El accidente ocurrió aproximadamente a las 15:40 en la intersección de la
avenida Alsina y la calle Ramón Gómez Cornet, en la capital provincial. Según
los primeros informes, Riemersma circulaba en su motocicleta cuando un perro se
cruzó súbitamente en su camino. Fiel a su naturaleza, maniobró para no
lastimarlo. La violenta caída le provocó graves traumatismos de cráneo y tórax.
Falleció horas después en el hospital, sin recuperar el conocimiento.</p>

<blockquote>
<p>"Hoy Santiago perdió al ángel de los perros."</p>
<p><em>— Mensaje que se viralizó en redes sociales tras conocerse la noticia</em></p>
</blockquote>

<h2>El Montecito de los Canichones: un refugio de 400 vidas</h2>

<p>Riemersma era el fundador y alma mater del refugio <em>El Montecito de los
Canichones</em>, uno de los más conocidos y queridos de la provincia. En sus
instalaciones convivían más de 400 perros rescatados de las calles de Santiago
del Estero, muchos de ellos con historias de maltrato, abandono y enfermedad.</p>

<p>Desde las redes sociales, el refugio se convirtió en un referente provincial
y nacional del proteccionismo animal. Miles de seguidores seguían sus
publicaciones, donde "El Polaco" mostraba el día a día de los animales,
impulsaba adopciones y denunciaba situaciones de crueldad. Su trabajo no tenía
horario, ni días libres, ni vacaciones.</p>

<h2>Una vida transformada por un accidente</h2>

<p>La historia de Eduardo Riemersma lleva una ironía que no pasa desapercibida.
En 1998, un grave accidente de tránsito lo dejó en coma y lo obligó a un año
entero de rehabilitación. Ese trance, en vez de quebrarlo, lo transformó: al
recuperarse, reorientó por completo sus prioridades y volcó su energía hacia
el cuidado de los animales y el servicio a la comunidad.</p>

<p>Veintiocho años después, otro accidente vial lo arrebató. Esta vez, tratando
de proteger a un animal.</p>

<h2>La conmoción que dejó</h2>

<p>La noticia se extendió en cuestión de horas por todos los grupos de
proteccionismo animal de la Argentina. Mensajes de condolencias llegaron desde
Córdoba, Buenos Aires y Tucumán. En Santiago del Estero, proteccionistas,
vecinos y adoptantes de animales del refugio se reunieron espontáneamente para
despedirlo.</p>

<p>El movimiento proteccionista de la provincia prometió honrar su legado:
continuar el trabajo en El Montecito de los Canichones y asegurar el bienestar
de los más de 400 perros que él cuidaba.</p>

<p>Eduardo "El Polaco" Groh Riemersma no tendrá más mañanas para rescatar perros.
Pero los que salvó lo recordarán con cada ladrido.</p>

<p><em>Fuentes: El Liberal, Nuevo Diario Web, Diario Panorama, Info del Estero</em></p>
"""

# URL canónica para deduplicación (usamos una de las fuentes)
URL_CANONICA = "https://www.elliberal.com.ar/nota/89817/2026/08/conmocion--murio-el-proteccionista-polaco-groh-riemersma"

FUENTE = "El Liberal / Nuevo Diario"

# Imagen: foto representativa del refugio / El Polaco (buscar en búsqueda web)
# Si no hay imagen, se publica sin featured image
IMAGEN_URL = None  # Se intentará buscar automáticamente


def _buscar_imagen() -> str | None:
    """Intenta obtener la imagen OG de la nota de El Liberal."""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept-Language": "es-AR,es;q=0.9",
    }
    try:
        from bs4 import BeautifulSoup
        resp = requests.get(URL_CANONICA, headers=headers, timeout=12)
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                img = tag["content"]
                logger.info(f"Imagen encontrada: {img[:80]}")
                return img
    except Exception as e:
        logger.warning(f"No se pudo obtener imagen: {e}")
    return None


def main():
    database.init_db()

    # Verificar si ya fue publicado
    if database.is_seen(URL_CANONICA):
        logger.warning("Esta nota ya fue publicada anteriormente. Abortando.")
        return

    logger.info("=== Publicando: El Polaco Riemersma ===")
    logger.info(f"Título: {TITULO}")

    # Buscar imagen
    img_url = _buscar_imagen()
    img_id = None
    if img_url:
        try:
            img_id = wordpress.upload_image(img_url, TITULO)
            logger.info(f"Imagen subida: ID={img_id}")
        except Exception as e:
            logger.warning(f"Error subiendo imagen: {e}")

    # Categorías: Santiago del Estero + Sociedad
    cat_ids = []
    for cat_name in ["Santiago del Estero", "Sociedad"]:
        try:
            cid = wordpress.get_or_create_category(cat_name)
            if cid:
                cat_ids.append(cid)
        except Exception:
            pass

    # Publicar en WordPress
    try:
        result = wordpress.create_post(
            title=TITULO,
            content=CUERPO_HTML,
            status="publish",
            featured_media=img_id,
            sticky=True,  # destacado por ser nota central local
            categories=cat_ids,
        )
    except Exception as e:
        logger.error(f"Error publicando en WordPress: {e}")
        return

    if not result:
        logger.error("WordPress no devolvió respuesta. Abortando.")
        return

    wp_id = result.get("id")
    wp_link = result.get("link", "")
    logger.info(f"✓ Publicado en WordPress: ID={wp_id} | {wp_link}")

    # Rotar sticky posts para que aparezca en el hero
    try:
        wordpress.rotate_sticky_posts(max_sticky=4)
        logger.info("✓ Sticky rotation ejecutada")
    except Exception as e:
        logger.warning(f"Error en rotate_sticky: {e}")

    # Registrar en DB para no re-publicar
    database.mark_seen(URL_CANONICA, TITULO, FUENTE)

    logger.info("\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info(f"PUBLICADO: {wp_link}")
    logger.info("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
    logger.info("")
    logger.info("COPY PARA REDES / FLYER:")
    logger.info(f"  TÍTULO: {TITULO}")
    logger.info(f"  COPY:   {COPY_REDES}")


if __name__ == "__main__":
    main()
