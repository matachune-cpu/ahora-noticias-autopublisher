"""
Publica en WP + IG + FB el anuncio de los abogados de Cristina Kirchner
sobre el reclamo ante la ONU por la causa Vialidad (15/09/2026).
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
logger = logging.getLogger("cristina_onu")

# ── CONSTANTES ────────────────────────────────────────────────────────────────

TITULO_WP = (
    "Los abogados de Cristina Kirchner anuncian novedades ante la ONU: "
    "piden suspender la inhabilitación perpetua y que le saquen la tobillera"
)

TITULO_FLYER = "URGENTE: Abogados de Cristina hacen anuncio clave sobre la ONU y su futuro electoral"

CATEGORIA = "Política"

URL_CANONICA = "https://tn.com.ar/politica/2026/09/15/los-abogados-de-cristina-kirchner-hacen-un-anuncio-de-relevancia-sobre-el-reclamo-ante-la-onu-por-la-causa-vialidad/"
FUENTE = "TN"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")

CUERPO_HTML = """
<p><strong>Los abogados de Cristina Fernández de Kirchner realizaron este martes un anuncio
de relevancia sobre el reclamo que presentaron ante el Comité de Derechos Humanos de la
Organización de las Naciones Unidas (ONU), en el marco de la condena dictada en la causa
Vialidad.</strong> Los letrados Carlos Beraldi, Rafael Valim y Javier Borrego brindaron una
conferencia de prensa en la que detallaron las novedades del expediente y el impacto que podría
tener en el futuro electoral de la ex presidenta.</p>

<h2>Qué pidieron ante la ONU</h2>

<p>En julio de 2026, el equipo de defensa presentó ante el Comité de Derechos Humanos de la ONU
una comunicación en la que denunció <strong>ocho violaciones al Pacto Internacional de Derechos
Civiles y Políticos</strong> cometidas durante el proceso judicial que derivó en la condena a
seis años de prisión domiciliaria y la inhabilitación perpetua para ejercer cargos públicos.</p>

<p>Entre los pedidos centrales, los abogados solicitaron <strong>medidas cautelares para suspender
la inhabilitación perpetua</strong> —que le impide a Kirchner ser candidata en cualquier elección—
y también reclamaron que se le retire la <strong>tobillera electrónica</strong> que lleva desde
que cumple arresto domiciliario. Además, pidieron que se eliminen las restricciones de visitas
y se le garantice acceso a espacios al aire libre.</p>

<h2>El argumento jurídico: "la perpetuidad viola el Pacto"</h2>

<p>La defensa sostiene que la inhabilitación perpetua "viola precedentes claros del Comité de
Derechos Humanos de la ONU" y que la condena fue producto de "evidente arbitrariedad judicial".
Rafael Valim —el reconocido abogado brasileño que formó parte del equipo defensor del expresidente
Luiz Inácio Lula da Silva durante su proceso judicial— fue uno de los firmantes del documento
presentado ante el organismo internacional.</p>

<p>Los letrados también cuestionaron la composición actual de la Corte Suprema de Justicia,
argumentando que afecta el Estado de derecho y el derecho a un recurso efectivo.</p>

<h2>El impacto electoral: el escenario de 2027</h2>

<p>El anuncio llega en un momento de alta tensión política, a menos de un año de las elecciones
legislativas de 2027. Si el Comité de Derechos Humanos de la ONU resolviera favorablemente las
medidas cautelares —algo que podría ocurrir en los próximos meses—, la inhabilitación que pesa
sobre Kirchner quedaría en suspenso y abriría la puerta a una eventual candidatura.</p>

<p>Sin embargo, se trata de un organismo de monitoreo: sus resoluciones no son vinculantes de
forma directa para el Estado argentino, por lo que su cumplimiento dependería de la voluntad
política del gobierno y de la reacción de la Justicia local. Una decisión sobre el fondo del
asunto podría demorar varios años.</p>

<h2>La causa Vialidad: el origen de todo</h2>

<p>Cristina Kirchner fue condenada en diciembre de 2022 por el Tribunal Oral Federal N° 2
en la causa conocida como Vialidad, por administración fraudulenta en perjuicio del Estado
en la obra pública en Santa Cruz durante su gestión como presidenta (2007–2015). La pena fue
de seis años de prisión e inhabilitación perpetua para ejercer cargos públicos. La condena
fue confirmada por la Cámara Federal de Casación Penal. La defensa apeló ante la Corte Suprema
y el proceso continúa abierto en la Justicia argentina.</p>

<p><em>Fuente: TN / Perfil / Ambito</em></p>
"""

# ── FUENTES DE IMAGEN ─────────────────────────────────────────────────────────

FUENTES_IMAGEN = [
    "https://tn.com.ar/politica/2026/09/15/los-abogados-de-cristina-kirchner-hacen-un-anuncio-de-relevancia-sobre-el-reclamo-ante-la-onu-por-la-causa-vialidad/",
    "https://www.infobae.com/politica/2026/07/29/cristina-kirchner-anuncio-que-llevara-su-condena-por-la-causa-vialidad-a-la-onu-con-asistencia-del-abogado-de-lula-da-silva/",
    "https://www.perfil.com/noticias/politica/en-vivo-los-abogados-de-cristina-kirchner-denuncian-proscripcion-e-irregularidades-en-la-causa-vialidad-ante-la-onu.phtml",
    "https://www.lanacion.com.ar/politica/",
    "https://www.clarin.com/politica/",
]


def _buscar_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                img = tag["content"]
                if img.startswith("http") and not any(s in img.lower() for s in _LOGO_SIGNALS):
                    logger.info(f"  Imagen: {img[:80]}")
                    return img
    except Exception as e:
        logger.debug(f"og:image {url}: {e}")
    return None


def _buscar_imagen() -> str | None:
    for url in FUENTES_IMAGEN:
        img = _buscar_og_image(url)
        if img:
            return img
    return None


def _generar_captions_gemini(wp_link: str) -> dict:
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")
        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            "Generá DOS textos para comunicar esta noticia política urgente:\n\n"
            "TITULAR: 'Los abogados de Cristina Kirchner hacen un anuncio clave ante la ONU'\n\n"
            "CONTEXTO: Los letrados Carlos Beraldi, Rafael Valim y Javier Borrego anunciaron hoy "
            "novedades sobre el reclamo presentado en julio 2026 ante el Comité de Derechos Humanos "
            "de la ONU por la condena en la causa Vialidad. Denunciaron 8 violaciones al Pacto "
            "Internacional de Derechos Civiles y Políticos. Piden medidas cautelares para suspender "
            "la inhabilitación perpetua (que le impide ser candidata) y que le retiren la tobillera "
            "electrónica. Si la ONU resuelve favorablemente, podría habilitar su candidatura en 2027. "
            "La condena original: 6 años de prisión domiciliaria e inhabilitación perpetua por "
            "administración fraudulenta en la obra pública en Santa Cruz.\n\n"
            "TEXTO 1 — Caption Instagram (máx 160 palabras):\n"
            "- Tono: urgente, informativo, que genere debate\n"
            "- Hook que detenga el scroll con la novedad\n"
            "- Datos clave del reclamo ante la ONU\n"
            "- Cerrá con: #CristinaKirchner #ONU #CausaVialidad #AhoraNoticias #Política\n\n"
            "TEXTO 2 — Copy Facebook (máx 80 palabras):\n"
            "- Arrancar con la noticia directa\n"
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
        fb = (
            "🚨 ÚLTIMO MOMENTO: Los abogados de Cristina Kirchner anunciaron novedades sobre "
            "su reclamo ante el Comité de Derechos Humanos de la ONU. Piden suspender la "
            "inhabilitación perpetua —que le impide ser candidata en 2027— y que le retiren "
            "la tobillera electrónica. El caso podría resolverse en los próximos meses.\n\n"
            f"Leé la nota completa → {wp_link}"
        )
        return {"instagram": ig, "facebook": fb}


def main():
    database.init_db()

    if database.is_published(URL_CANONICA):
        logger.warning("Esta nota ya fue publicada. Abortando.")
        return

    logger.info("=== Publicando: Abogados de Cristina - Anuncio ONU ===")

    # ── IMAGEN ────────────────────────────────────────────────────────────────
    logger.info("Buscando imagen...")
    img_url = _buscar_imagen()
    if not img_url:
        logger.error("Sin imagen. Abortando.")
        return

    # ── WORDPRESS ─────────────────────────────────────────────────────────────
    wp_img_id = None
    try:
        result = wordpress.upload_image(
            image_url=img_url,
            filename=f"cristina-onu-{datetime.now().strftime('%Y%m%d')}.jpg",
        )
        if isinstance(result, tuple):
            wp_img_id, _ = result
    except Exception as e:
        logger.warning(f"Imagen WP fallida: {e}")

    cat_ids = []
    for cat in ["Política", "Nacionales"]:
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
        upload_result = wordpress.upload_image(flyer_path, f"flyer-cristina-onu-{ts}.jpg")
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
