"""
Publica en WP + IG + FB la nota sobre la advertencia militar británica
tras las medidas de Milei por Malvinas.
Ángulo: ¿Milei jugará el juego de la guerra o apostará a la diplomacia?
"""
import logging
import os
import tempfile
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

import config
import database
from flyer_generator import generate_flyer
from publishers import wordpress, instagram, facebook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("malvinas_uk_alerta")

# ── CONSTANTES ────────────────────────────────────────────────────────────────

TITULO_WP = (
    "Gran Bretaña puso en alerta sus Fuerzas Armadas tras las medidas de Milei "
    "por Malvinas: ¿guerra o diplomacia?"
)

TITULO_FLYER = (
    "Gran Bretaña en alerta militar por Malvinas: ¿Milei jugará el juego de la guerra?"
)

CATEGORIA = "Malvinas"

URL_CANONICA = "https://todonocias.info/4xbu4eO"
FUENTE = "TN Todo Noticias"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")

CUERPO_HTML = """
<p>El gobierno británico salió a responder con dureza las medidas anunciadas por el
presidente Javier Milei en torno a la soberanía argentina sobre las Islas Malvinas.
Downing Street subrayó que el apoyo del Reino Unido a las islas es "inquebrantable"
y alertó que sus Fuerzas Armadas están en máxima disposición.</p>

<p>El primer ministro Andy Burnham "apoya plenamente el deseo de los isleños de
seguir siendo un territorio británico de ultramar", según confirmaron fuentes
oficiales del gobierno de Londres.</p>

<blockquote>
<p>"Nuestras Fuerzas Armadas están en alerta las 24 horas del día, los siete días
de la semana, para proteger al Reino Unido y nuestros intereses."</p>
<p><em>— Gobierno británico, Downing Street</em></p>
</blockquote>

<h2>El origen del cruce: Milei y "las Malvinas son nuestro futuro"</h2>

<p>La declaración de Londres llegó como respuesta directa a las palabras de Milei,
quien en los últimos días destacó que "las Malvinas son nuestro futuro" y respaldó
la política de bloqueo a la exploración petrolera de empresas extranjeras en las
aguas que Argentina reclama como propias.</p>

<p>La cadena nacional de Milei sobre la causa Malvinas generó una ola de apoyo
transversal en la política argentina —con figuras del peronismo como el senador
Gerardo Zamora respaldando públicamente la postura presidencial— y ahora también
una reacción formal y contundente del Reino Unido.</p>

<h2>¿Guerra o diplomacia? La pregunta que divide aguas</h2>

<p>La respuesta británica abre un interrogante central para la política exterior
argentina: ¿hasta dónde está dispuesto a llegar Milei en su reclamo soberano?</p>

<p>El gobierno nacional tiene dos caminos bien diferenciados. Por un lado, la
escalada retórica y la presión económica —bloquear licencias, impedir exploraciones,
denunciar ante organismos internacionales— que no implica conflicto armado pero sí
un enfrentamiento diplomático sostenido con Londres. Por el otro, la vía del diálogo
bilateral, que históricamente Argentina ha intentado sin éxito, dado que Gran Bretaña
se niega a discutir soberanía.</p>

<p>La pregunta que hoy circula en los pasillos de la Cancillería argentina es si
Milei —con su perfil confrontativo y su retórica de "no dar un paso atrás"— se
dejará llevar por la lógica de la escalada que Londres parece buscar con su alerta
militar, o si en cambio optará por profundizar la vía diplomática y jurídica
internacional que mencionó en su cadena nacional.</p>

<h2>El contexto regional</h2>

<p>La tensión llega en un momento en que Argentina está tratando de reconstruir
alianzas regionales y fortalecer su posición en foros internacionales como la ONU,
la OEA y el MERCOSUR en torno a la causa Malvinas. Una respuesta belicista
comprometería ese camino; una respuesta mesurada podría ser leída como debilidad
por sectores que esperan del gobierno una postura más firme.</p>

<p>Por ahora, el gobierno argentino no respondió oficialmente a la advertencia de
Downing Street.</p>

<p><em>Fuente: TN Todo Noticias</em></p>
"""

# ── FUENTES DE IMAGEN ─────────────────────────────────────────────────────────

FUENTES_IMAGEN = [
    "https://www.tn.com.ar/politica/",
    "https://www.tn.com.ar/internacional/",
    "https://www.infobae.com/politica/",
    "https://www.clarin.com/politica/",
]

# Palabras clave para buscar el artículo correcto en portadas
KEYWORDS_BUSQUEDA = ["malvinas", "britanico", "britain", "burnham", "fuerzas armadas"]


def _buscar_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                img = tag["content"]
                if img.startswith("http") and not any(s in img.lower() for s in _LOGO_SIGNALS):
                    return img
    except Exception as e:
        logger.debug(f"og:image {url}: {e}")
    return None


def _buscar_imagen_noticia() -> str | None:
    """Busca imagen del artículo sobre la advertencia británica."""
    for base_url in FUENTES_IMAGEN:
        try:
            resp = requests.get(base_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for a in soup.find_all("a", href=True):
                href = a["href"]
                text = (a.get_text(strip=True) + " " + href).lower()
                if any(kw in text for kw in KEYWORDS_BUSQUEDA):
                    if not href.startswith("http"):
                        from urllib.parse import urlparse
                        p = urlparse(base_url)
                        href = f"{p.scheme}://{p.netloc}{href}"
                    img = _buscar_og_image(href)
                    if img:
                        logger.info(f"Imagen encontrada: {img[:80]}")
                        return img
        except Exception as e:
            logger.debug(f"Error buscando imagen en {base_url}: {e}")

    # Fallback: og:image de la portada de TN
    return _buscar_og_image("https://www.tn.com.ar/politica/")


def _generar_captions_gemini(wp_link: str) -> dict:
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")
        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            "Generá DOS textos para esta nota de geopolítica de alto impacto:\n\n"
            "TITULAR: 'Gran Bretaña puso en alerta sus Fuerzas Armadas tras las medidas "
            "de Milei por Malvinas: ¿guerra o diplomacia?'\n\n"
            "CONTEXTO: Milei dijo 'las Malvinas son nuestro futuro' y tomó medidas para "
            "bloquear la exploración petrolera extranjera. Downing Street respondió: el PM "
            "Andy Burnham 'apoya plenamente que los isleños sigan siendo territorio británico' "
            "y advirtió que 'nuestras Fuerzas Armadas están en alerta 24/7 para proteger "
            "nuestros intereses'. La pregunta que todos se hacen: ¿Milei jugará el juego "
            "de la guerra que le tiende Londres, o apostará a la diplomacia internacional?\n\n"
            "TEXTO 1 — Caption Instagram (máx 160 palabras):\n"
            "- Hook que genere ansiedad e interrogante genuino\n"
            "- Tono: urgente, analítico, sin tomar partido\n"
            "- Emojis estratégicos (🇦🇷🇬🇧⚔️🕊️)\n"
            "- Cerrá con: #Malvinas #Argentina #AhoraNoticias #Política\n\n"
            "TEXTO 2 — Copy Facebook (máx 80 palabras):\n"
            "- Arranca con la advertencia más fuerte de Gran Bretaña\n"
            "- Sin hashtags\n"
            f"- Cerrá con: 'Leé la nota completa → {wp_link}'\n\n"
            "Respondé EXACTAMENTE:\n"
            "===INSTAGRAM===\n[caption]\n===FACEBOOK===\n[copy]\n"
        )

        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = response.text.strip()

        ig, fb = "", ""
        if "===INSTAGRAM===" in raw and "===FACEBOOK===" in raw:
            parts = raw.split("===FACEBOOK===")
            ig = parts[0].replace("===INSTAGRAM===", "").strip()
            fb = parts[1].strip()
        else:
            ig = raw
            fb = raw[:300]

        logger.info(f"Gemini OK (IG={len(ig)}c / FB={len(fb)}c)")
        return {"instagram": ig, "facebook": fb}

    except Exception as e:
        logger.warning(f"Gemini no disponible: {e}. Usando respaldo.")
        ig = (
            "🇬🇧⚔️ GRAN BRETAÑA ALERTA SUS FUERZAS ARMADAS\n\n"
            "Después de que Milei dijera 'las Malvinas son nuestro futuro' y bloqueara "
            "la exploración petrolera extranjera, Downing Street respondió con dureza:\n\n"
            "🔴 'Nuestras Fuerzas Armadas están en alerta 24/7 para proteger nuestros intereses'\n"
            "🔴 El PM Andy Burnham apoya que los isleños sigan siendo territorio británico\n\n"
            "🇦🇷🕊️ La pregunta que divide aguas: ¿Milei jugará el juego de la guerra "
            "que le tiende Londres, o apostará a la diplomacia internacional?\n\n"
            "#Malvinas #Argentina #AhoraNoticias #Política"
        )
        fb = (
            "🇬🇧 'NUESTRAS FUERZAS ARMADAS ESTÁN EN ALERTA': Gran Bretaña respondió con "
            "dureza a las medidas de Milei por Malvinas. Downing Street activó su postura "
            "militar y el mundo espera: ¿Argentina irá por la guerra o por la diplomacia?\n\n"
            f"Leé la nota completa → {wp_link}"
        )
        return {"instagram": ig, "facebook": fb}


def main():
    database.init_db()

    already = database.is_published(URL_CANONICA)
    if already:
        logger.warning("Esta nota ya fue publicada. Abortando.")
        return

    logger.info("=== Publicando: Advertencia militar británica por Malvinas ===")

    # ── IMAGEN ────────────────────────────────────────────────────────────────
    logger.info("Buscando imagen del artículo...")
    img_url = _buscar_imagen_noticia()
    if not img_url:
        logger.error("Sin imagen. Abortando.")
        return

    # ── WORDPRESS ─────────────────────────────────────────────────────────────
    wp_img_id = None
    try:
        result = wordpress.upload_image(image_url=img_url,
                                        filename=f"malvinas-uk-alerta-{datetime.now().strftime('%Y%m%d')}.jpg")
        if isinstance(result, tuple):
            wp_img_id, _ = result
    except Exception as e:
        logger.warning(f"Imagen WP fallida: {e}")

    cat_ids = []
    for cat in ["Malvinas", "Política", "Internacional"]:
        try:
            cid = wordpress.get_or_create_category(cat)
            if cid:
                cat_ids.append(cid)
        except Exception:
            pass

    try:
        wp_result = wordpress.create_post(
            title=TITULO_WP,
            body_html=CUERPO_HTML,
            original_url=URL_CANONICA,
            source_name=FUENTE,
            featured_media_id=wp_img_id,
            sticky=True,
            categories=cat_ids,
        )
    except Exception as e:
        logger.error(f"Error WP: {e}")
        return

    if not wp_result:
        logger.error("WP no respondió.")
        return

    if isinstance(wp_result, tuple):
        wp_id, wp_link = wp_result
    else:
        wp_id = wp_result.get("id") if isinstance(wp_result, dict) else None
        wp_link = wp_result.get("link", "https://ahoranoticias.com.ar") if isinstance(wp_result, dict) else "https://ahoranoticias.com.ar"

    logger.info(f"✓ WordPress: ID={wp_id} | {wp_link}")

    if wp_id:
        try:
            wordpress.rotate_sticky_posts(new_post_ids=[int(wp_id)], max_sticky=4)
        except Exception as e:
            logger.warning(f"Rotate sticky: {e}")

    database.mark_published(URL_CANONICA, TITULO_WP, FUENTE,
                            wp_post_id=str(wp_id) if wp_id else None)

    # ── CAPTIONS ──────────────────────────────────────────────────────────────
    captions = _generar_captions_gemini(wp_link)
    logger.info(f"\n--- INSTAGRAM ---\n{captions['instagram']}\n")
    logger.info(f"--- FACEBOOK ---\n{captions['facebook']}\n")

    # ── FLYER ─────────────────────────────────────────────────────────────────
    flyer_path = None
    flyer_url = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name

        generate_flyer(
            title=TITULO_FLYER,
            source_name="Ahora Noticias",
            article_image_url=img_url,
            template_path=config.FLYER_TEMPLATE_PATH,
            output_path=flyer_path,
            categoria=CATEGORIA,
        )
        logger.info("✓ Flyer generado")

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        upload_result = wordpress.upload_image(flyer_path, f"flyer-malvinas-uk-{ts}.jpg")
        if isinstance(upload_result, tuple):
            _, flyer_url = upload_result
        logger.info(f"✓ Flyer en WP: {(flyer_url or '')[:80]}")
    except Exception as e:
        logger.error(f"Error flyer: {e}")
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

    if not flyer_url:
        logger.error("Sin URL de flyer. Abortando redes.")
        return

    # ── INSTAGRAM ─────────────────────────────────────────────────────────────
    ig_id = None
    try:
        ig_id = instagram.post_image(
            image_path=None,
            caption=captions["instagram"],
            public_image_url=flyer_url,
        )
        logger.info(f"✓ Instagram: {'ID=' + str(ig_id) if ig_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Instagram: {e}")

    # ── FACEBOOK ──────────────────────────────────────────────────────────────
    fb_id = None
    try:
        fb_id = facebook.post_link(
            title=TITULO_WP,
            wp_post_url=wp_link,
            original_url=wp_link,
            image_url=flyer_url,
            caption=captions["facebook"],
        )
        logger.info(f"✓ Facebook: {'ID=' + str(fb_id) if fb_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Facebook: {e}")

    logger.info(f"\n{'━'*55}")
    logger.info(f"  WP: {wp_link}")
    logger.info(f"  IG: {ig_id or 'falló'}")
    logger.info(f"  FB: {fb_id or 'falló'}")
    logger.info(f"{'━'*55}")


if __name__ == "__main__":
    main()
