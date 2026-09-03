"""
Publica en Instagram y Facebook la nota sobre GSFAR (estafa piramidal).
La nota ya está en WordPress. Este script solo genera flyer + redes.
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
from flyer_generator import generate_flyer
from publishers import wordpress, instagram, facebook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("redes_gsfar")

WP_POST_URL = "https://ahoranoticias.com.ar/gsfar-estafa-piramidal-alerta-en-santiago-del-estero/"

TITULO_FLYER = "GSFAR: la app que imita a PETA y promete duplicar tu dinero — alertan que es una estafa piramidal"

CATEGORIA_FLYER = "Economía"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

FUENTES_IMAGEN = [
    "https://www.elliberal.com.ar/nota/90400/2026/09/alerta-en-santiago-del-estero--gsfar-la-app-que-paga-rendimientos-exorbitantes-e-imita-el-modelo-de-peta",
    "https://www.msn.com/es-ar/noticias/other/los-detalles-de-la-nueva-estafa-piramidal-en-santiago-del-estero/vi-AA1soiyP",
]

_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")


def _buscar_imagen() -> str | None:
    for url in FUENTES_IMAGEN:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for prop in ["og:image", "twitter:image"]:
                tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
                if tag and tag.get("content"):
                    img = tag["content"]
                    if img.startswith("http") and not any(s in img.lower() for s in _LOGO_SIGNALS):
                        logger.info(f"Imagen: {img[:80]}")
                        return img
        except Exception as e:
            logger.debug(f"{url}: {e}")
    return None


def _generar_captions_gemini() -> dict:
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")
        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            "Generá DOS textos para la siguiente nota de alerta económica:\n\n"
            "TITULAR: 'GSFAR ¿Estafa piramidal? Alerta en Santiago del Estero'\n\n"
            "CONTEXTO: GSFAR (Gensolar Finanzas AR) es una nueva app de 'inversión en energías renovables' "
            "que está captando inversores en Santiago del Estero con promesas de rendimientos exorbitantes "
            "y duplicar el capital en pocos días. Especialistas la identifican como un esquema Ponzi "
            "piramidal en fase inicial, que imita el modelo de PETA — la plataforma que colapsó en 2024 "
            "y dejó a miles de familias santiagueñas sin dinero. Los usuarios actuales dicen cobrar, "
            "pero eso es típico del inicio de una pirámide. Ya se expande a Catamarca, La Rioja, Corrientes y Chaco.\n\n"
            "TEXTO 1 — Caption Instagram (máx 180 palabras):\n"
            "- Hook de alarma que detenga el scroll\n"
            "- Tono: urgente, informativo, responsable — esto puede hacerle perder dinero a gente real\n"
            "- Emojis con criterio (⚠️🚨💰 donde corresponda)\n"
            "- Cerrá con: #SantiagoDelEstero #Economía #AhoraNoticias #AlertaEstafa\n\n"
            "TEXTO 2 — Copy Facebook (máx 100 palabras):\n"
            "- Directo y alarmante desde la primera línea\n"
            "- Sin hashtags\n"
            "- Cerrá con: 'Leé la nota completa →'\n\n"
            "Respondé EXACTAMENTE así:\n"
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

        logger.info(f"Captions Gemini OK (IG: {len(ig)}c / FB: {len(fb)}c)")
        return {"instagram": ig, "facebook": fb}

    except Exception as e:
        logger.warning(f"Gemini no disponible: {e}. Usando respaldo.")
        ig = (
            "⚠️ ALERTA EN SANTIAGO DEL ESTERO\n\n"
            "GSFAR, la nueva app que promete duplicar tu dinero invirtiendo en 'energías renovables', "
            "está siendo señalada por especialistas como una estafa piramidal Ponzi en su fase inicial.\n\n"
            "🔴 Imita el modelo de PETA — la plataforma que en 2024 dejó a miles de familias santiagueñas sin sus ahorros.\n"
            "🔴 Promete rendimientos imposibles en pocos días.\n"
            "🔴 Ya se expande a Catamarca, La Rioja, Corrientes y Chaco.\n\n"
            "Que alguien te diga que está cobrando NO significa que es segura — así funciona toda pirámide al principio.\n\n"
            "Informate antes de invertir. Compartí esta alerta.\n\n"
            "#SantiagoDelEstero #Economía #AhoraNoticias #AlertaEstafa"
        )
        fb = (
            "⚠️ ALERTA: GSFAR, la app que promete duplicar tu dinero en días, es señalada como estafa piramidal Ponzi. "
            "Imita el modelo de PETA, que en 2024 dejó a miles de familias santiagueñas sin sus ahorros. "
            "Ya se expande por el NOA y el Litoral. No inviertas sin informarte.\n\n"
            "Leé la nota completa →"
        )
        return {"instagram": ig, "facebook": fb}


def main():
    logger.info("=== Redes sociales: GSFAR estafa piramidal ===")

    img_url = _buscar_imagen()
    if not img_url:
        logger.error("Sin imagen. Abortando.")
        return

    captions = _generar_captions_gemini()
    logger.info(f"\n--- INSTAGRAM ---\n{captions['instagram']}\n")
    logger.info(f"--- FACEBOOK ---\n{captions['facebook']}\n")

    # Generar flyer
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
            categoria=CATEGORIA_FLYER,
        )
        logger.info("✓ Flyer generado")

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        upload_result = wordpress.upload_image(flyer_path, f"flyer-gsfar-{ts}.jpg")
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
        logger.error("Sin URL pública del flyer. Abortando redes.")
        return

    # Instagram
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

    # Facebook
    fb_id = None
    try:
        fb_caption = f"{captions['facebook']}\n\n{WP_POST_URL}"
        fb_id = facebook.post_link(
            title=TITULO_FLYER,
            wp_post_url=WP_POST_URL,
            original_url=WP_POST_URL,
            image_url=flyer_url,
            caption=fb_caption,
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
