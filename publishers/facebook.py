import requests
import logging
import time
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"
WP_DOMAIN = "ahoranoticias.com.ar"   # dominio propio — NUNCA linkear a otro


def _like_post(post_id: str, token: str) -> None:
    """
    Da 'Me gusta' al post desde la propia página inmediatamente después
    de publicarlo. Esto activa la señal de engagement en el algoritmo
    del New Pages Experience (NPE) de Facebook, que de lo contrario
    no distribuye posts API en el feed móvil sin engagement inicial.
    """
    try:
        r = requests.post(
            f"{GRAPH_URL}/{post_id}/likes",
            data={"access_token": token},
            timeout=15,
        )
        if r.ok:
            logger.info(f"Facebook: like propio agregado al post {post_id}")
        else:
            logger.warning(f"Facebook like error: {r.text[:100]}")
    except Exception as e:
        logger.warning(f"Facebook like error (no fatal): {e}")


def post_link(
    title: str,
    wp_post_url: str,
    original_url: str,
    image_url: str = None,
) -> str | None:
    """
    Publica en Facebook como link post estándar y da like automático.

    El like de la propia página activa la señal de engagement que el
    algoritmo NPE móvil necesita para mostrar el post en el feed.
    Sin ese like inicial, los posts API quedan invisibles en móvil
    aunque están públicos y se ven correctamente en escritorio.

    REGLA CRÍTICA: si wp_post_url no es de nuestro sitio, se cancela.
    NUNCA se linkea a la fuente original (Infobae, El Liberal, etc.).
    """
    link = (wp_post_url or "").strip()
    if not link or WP_DOMAIN not in link:
        logger.error(
            f"Facebook BLOQUEADO: '{link}' no pertenece a {WP_DOMAIN}. "
            f"Publicación cancelada para evitar linkear a fuentes externas."
        )
        return None

    page  = config.FB_PAGE_ID
    token = config.META_ACCESS_TOKEN

    message = f"\U0001f4f0 {title}\n\nLeé la nota completa en nuestro sitio \U0001f447"

    try:
        r = requests.post(
            f"{GRAPH_URL}/{page}/feed",
            data={
                "message": message,
                "link": link,
                "access_token": token,
            },
            timeout=30,
        )
        r.raise_for_status()
        post_id = r.json().get("id")
        logger.info(f"Facebook: link post publicado ID={post_id} | {link}")

        # Dar like propio para activar distribución en feed móvil (NPE)
        if post_id:
            time.sleep(2)
            _like_post(post_id, token)

        return post_id

    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Facebook HTTP error: {e} | "
            f"response={e.response.text[:300] if e.response is not None else 'N/A'}"
        )
        return None
    except Exception as e:
        logger.error(f"Facebook post_link error: {e}")
        return None
