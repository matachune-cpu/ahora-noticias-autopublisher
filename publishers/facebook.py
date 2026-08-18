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
    caption: str = None,
) -> str | None:
    """
    Publica en Facebook apuntando a ahoranoticias.com.ar.

    GUARD CLAUSE DE IMAGEN: Esta función solo debe llamarse desde el pipeline
    principal cuando imagen_validada=True (validada por image_resolver.py).
    Sin imagen_url, se llama a _post_link_fallback como contingencia, pero
    el flujo normal garantiza que image_url siempre esté presente.

    Si hay imagen: publica como FOTO (endpoint /photos) con la URL como texto
    plano en el mensaje — el algoritmo de Meta no penaliza este formato como
    los link posts (3-5× más alcance orgánico). Da like propio al publicar.

    Si no hay imagen (no debería ocurrir en flujo normal): fallback a link post
    con warning prominente.

    REGLA CRÍTICA: si wp_post_url no es de nuestro sitio, se cancela.
    NUNCA se linkea a la fuente original.
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

    if image_url:
        return _post_photo(page, token, image_url, caption or title, link)
    else:
        # Esto no debería ocurrir en el flujo normal (image_resolver garantiza imagen validada)
        logger.warning(
            "Facebook: post_link llamado SIN imagen validada — "
            "esto no debería ocurrir en el flujo normal. Usando fallback de link post."
        )
        return _post_link_fallback(page, token, title, link, caption)


def _post_photo(page: str, token: str, image_url: str, caption: str, link: str) -> str | None:
    """
    Publica como foto (endpoint /photos). Mayor alcance orgánico que link posts
    porque Meta no detecta intención de sacar usuarios de la plataforma.
    La URL va como texto plano al final del mensaje.
    """
    message = f"{caption}\n\n🔗 {link}"
    try:
        r = requests.post(
            f"{GRAPH_URL}/{page}/photos",
            data={
                "url": image_url,
                "message": message,
                "access_token": token,
            },
            timeout=30,
        )
        r.raise_for_status()
        post_id = r.json().get("id") or r.json().get("post_id")
        logger.info(f"Facebook: foto publicada ID={post_id}")

        if post_id:
            time.sleep(2)
            _like_post(post_id, token)

        return post_id
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Facebook photo post HTTP error: {e} | "
            f"response={e.response.text[:300] if e.response is not None else 'N/A'}"
        )
        return None
    except Exception as e:
        logger.error(f"Facebook _post_photo error: {e}")
        return None


def _post_link_fallback(page: str, token: str, title: str, link: str, caption: str = None) -> str | None:
    """Fallback a link post cuando no hay imagen disponible."""
    message = caption or f"📰 {title}\n\nLeé la nota completa en nuestro sitio 👇"
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
        logger.info(f"Facebook: link post (sin imagen) ID={post_id} | {link}")

        if post_id:
            time.sleep(2)
            _like_post(post_id, token)

        return post_id
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Facebook link fallback HTTP error: {e} | "
            f"response={e.response.text[:300] if e.response is not None else 'N/A'}"
        )
        return None
    except Exception as e:
        logger.error(f"Facebook _post_link_fallback error: {e}")
        return None


def delete_post(post_id: str) -> bool:
    """
    Elimina un post de Facebook por su ID (formato PAGE_ID_POST_ID o solo POST_ID).
    Retorna True si se eliminó correctamente.
    """
    token = config.META_ACCESS_TOKEN
    try:
        r = requests.delete(
            f"{GRAPH_URL}/{post_id}",
            params={"access_token": token},
            timeout=15,
        )
        r.raise_for_status()
        success = r.json().get("success", False)
        if success:
            logger.info(f"Facebook: post eliminado ID={post_id}")
        else:
            logger.warning(f"Facebook: respuesta inesperada al eliminar {post_id}: {r.text[:200]}")
        return bool(success)
    except requests.exceptions.HTTPError as e:
        logger.error(
            f"Facebook delete_post HTTP error: {e} | "
            f"response={e.response.text[:300] if e.response is not None else 'N/A'}"
        )
        return False
    except Exception as e:
        logger.error(f"Facebook delete_post error: {e}")
        return False
