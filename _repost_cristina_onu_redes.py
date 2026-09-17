"""
Re-publica en IG + FB la nota de Cristina/ONU ya existente en WordPress.
Usa los IDs de media y post conocidos (post 16771, flyer 16773).
"""
import logging
import os
from dotenv import load_dotenv

load_dotenv()

from publishers import wordpress, instagram, facebook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("repost_cristina_onu")

WP_POST_ID = 16771
FLYER_MEDIA_ID = 16773

CAPTION_IG = (
    "🚨 ÚLTIMO MOMENTO | Los abogados de Cristina Kirchner hicieron un anuncio "
    "de relevancia sobre el reclamo ante la ONU.\n\n"
    "Beraldi, Valim y Borrego denunciaron 8 violaciones al Pacto Internacional de "
    "Derechos Civiles ante el Comité de Derechos Humanos:\n\n"
    "⚖️ Piden suspender la INHABILITACIÓN PERPETUA\n"
    "📿 Reclaman que le saquen la TOBILLERA ELECTRÓNICA\n"
    "🗳️ Si prospera, podría SER CANDIDATA en 2027\n\n"
    "Una resolución cautelar podría llegar en los próximos meses. "
    "¿La ONU le abrirá el camino electoral?\n\n"
    "#CristinaKirchner #ONU #CausaVialidad #AhoraNoticias #Política"
)


def _get_wp_data():
    import requests
    wp_url = os.getenv("WP_URL", "").rstrip("/")
    user = os.getenv("WP_USERNAME", "")
    pwd = os.getenv("WP_APP_PASSWORD", "")
    auth = (user, pwd)

    post_resp = requests.get(f"{wp_url}/wp-json/wp/v2/posts/{WP_POST_ID}", auth=auth, timeout=15)
    post_resp.raise_for_status()
    wp_link = post_resp.json().get("link", "https://ahoranoticias.com.ar")

    media_resp = requests.get(f"{wp_url}/wp-json/wp/v2/media/{FLYER_MEDIA_ID}", auth=auth, timeout=15)
    media_resp.raise_for_status()
    flyer_url = media_resp.json().get("source_url", "")

    return wp_link, flyer_url


def main():
    logger.info("=== Re-publicando en redes: Cristina/ONU ===")

    try:
        wp_link, flyer_url = _get_wp_data()
        logger.info(f"WP link: {wp_link}")
        logger.info(f"Flyer:   {flyer_url[:80]}")
    except Exception as e:
        logger.error(f"Error obteniendo datos de WP: {e}")
        return

    caption_fb = (
        "🚨 ÚLTIMO MOMENTO: Los abogados de Cristina Kirchner anunciaron novedades sobre "
        "su reclamo ante el Comité de Derechos Humanos de la ONU. Piden suspender la "
        "inhabilitación perpetua —que le impide ser candidata en 2027— y que le retiren "
        f"la tobillera electrónica. El caso podría resolverse en los próximos meses.\n\n"
        f"Leé la nota completa → {wp_link}"
    )

    ig_id = None
    try:
        ig_id = instagram.post_image(
            image_path=None,
            caption=CAPTION_IG,
            public_image_url=flyer_url,
        )
        logger.info(f"✓ Instagram: {'ID=' + str(ig_id) if ig_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Instagram: {e}")

    fb_id = None
    try:
        fb_id = facebook.post_link(
            title="Los abogados de Cristina Kirchner anuncian novedades ante la ONU",
            wp_post_url=wp_link,
            original_url=wp_link,
            image_url=flyer_url,
            caption=caption_fb,
        )
        logger.info(f"✓ Facebook: {'ID=' + str(fb_id) if fb_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Facebook: {e}")

    logger.info(f"\n{'━'*55}")
    logger.info(f"  IG: {ig_id or 'falló'}")
    logger.info(f"  FB: {fb_id or 'falló'}")
    logger.info(f"{'━'*55}")


if __name__ == "__main__":
    main()
