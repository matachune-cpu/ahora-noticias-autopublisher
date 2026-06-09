import requests
import logging
import config

logger = logging.getLogger(__name__)

GRAPH_URL = "https://graph.facebook.com/v19.0"
WP_DOMAIN = "ahoranoticias.com.ar"   # dominio propio — NUNCA linkear a otro


def post_link(
    title: str,
    wp_post_url: str,
    original_url: str,
    image_url: str = None,
) -> str | None:
    """
    Publica en Facebook como LINK POST estándar apuntando a ahoranoticias.com.ar.

    Este método crea un post de tipo "link" que aparece correctamente
    en el feed principal tanto en escritorio como en la app móvil.
    Facebook scrapea el og:image del artículo de WordPress (Yoast SEO
    garantiza que esté configurado correctamente con la imagen destacada).

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

    message = f"📰 {title}\n\nLeé la nota completa en nuestro sitio 👇"
    page  = config.FB_PAGE_ID
    token = config.META_ACCESS_TOKEN

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
