"""
Genera flyer con Gemini-caption y publica en Instagram.
Nota: Eduardo "El Polaco" Groh Riemersma.
"""
import io
import logging
import os
import tempfile

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

import config
from flyer_generator import generate_flyer
from publishers import wordpress, instagram

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("flyer_polaco")

TITULO_FLYER = "El hombre que salvó a más de 400 perros murió intentando no atropellar a uno"

CATEGORIA = "Santiago del Estero"

# Fuentes donde buscar imagen (probadas en GitHub Actions, fuera del proxy local)
FUENTES_IMAGEN = [
    "https://nuevodiarioweb.com.ar/policiales/info-santiago-estero-murio-el-polaco-riemersma-tras-sufrir-un-grave-accidente-en-moto.htm",
    "https://nuevodiarioweb.com.ar/especiales/info-santiago-estero-quien-era-eduardo-el-polaco-groh-riemersma-una-vida-marcada-por-el-rescate-de-animales.htm",
    "https://www.radiolv11.com.ar/noticia/quien-era-eduardo-el-polaco-groh-riemersma-el-proteccionista-santiagueno-que-dedico-su-vida-al-rescate-animal",
    "https://www.diariopanorama.com/noticia/564500/conmocion-murio-polaco-riemersma-tras-grave-accidente-sufrio-este-jueves-moto",
    "https://infodelestero.com/2026/08/27/consternacion-por-la-muerte-de-el-polaco-hoy-santiago-perdio-al-angel-de-los-perros",
    "https://www.elliberal.com.ar/nota/89817/2026/08/conmocion--murio-el-proteccionista-polaco-groh-riemersma",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

# Señales de logo/imagen genérica — descartar
_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")


def _buscar_imagen_og() -> str | None:
    """Recorre las fuentes en orden hasta encontrar una imagen OG válida."""
    for url in FUENTES_IMAGEN:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            for prop in ["og:image", "twitter:image"]:
                tag = (
                    soup.find("meta", property=prop)
                    or soup.find("meta", attrs={"name": prop})
                )
                if tag and tag.get("content"):
                    img = tag["content"]
                    if not any(s in img.lower() for s in _LOGO_SIGNALS) and img.startswith("http"):
                        logger.info(f"Imagen encontrada en {url}: {img[:80]}")
                        return img
        except Exception as e:
            logger.debug(f"Error en {url}: {e}")
    return None


def _generar_caption_gemini() -> str:
    """Usa Gemini para generar el caption de Instagram."""
    try:
        from google import genai

        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("GEMINI_API_KEY no configurada")

        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero, Argentina.\n\n"
            "Escribí el caption para Instagram de esta nota. Instrucciones:\n"
            "- Tono: respetuoso, emotivo y con fuerza. Es una pérdida que conmocionó a toda la provincia.\n"
            "- Usá emojis con criterio, no en exceso.\n"
            "- Empezá con un hook poderoso que detenga el scroll.\n"
            "- Contá brevemente qué pasó y quién era El Polaco.\n"
            "- Cerrá con: #SantiagoDelEstero #ElPolaco #ProteccionAnimal #AhoraNoticias\n"
            "- Máximo 220 palabras.\n\n"
            "Titular: \"El hombre que salvó a más de 400 perros murió intentando no atropellar a uno\"\n\n"
            "Contexto: Eduardo 'El Polaco' Groh Riemersma, 49 años, fundador del refugio "
            "El Montecito de los Canichones (más de 400 perros rescatados), murió el jueves "
            "en Santiago del Estero al esquivar a un perro que se cruzó en su moto. "
            "Sufrió traumatismos de cráneo y tórax. En 1998 ya había sobrevivido a un accidente "
            "que lo dejó en coma; esa experiencia lo llevó a dedicar su vida al rescate animal. "
            "Su muerte generó una conmoción enorme en el movimiento proteccionista de la provincia.\n\n"
            "Respondé solo con el caption listo para pegar. Sin texto extra."
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        caption = response.text.strip()
        logger.info(f"Caption Gemini generado ({len(caption)} chars)")
        return caption

    except Exception as e:
        logger.warning(f"Gemini no disponible: {e}. Usando caption de respaldo.")
        return (
            "😔 Vivió para salvarlos. Murió intentando no lastimarlos.\n\n"
            "Eduardo 'El Polaco' Groh Riemersma, fundador del refugio El Montecito de los "
            "Canichones, falleció el jueves en Santiago del Estero tras esquivar a un perro "
            "que se cruzó en su moto. Tenía 49 años y más de 400 perros bajo su cuidado.\n\n"
            "Fue referente del proteccionismo animal en toda la provincia. Su historia, su "
            "refugio y esos 400 perros son su legado.\n\n"
            "🐾 Que descanse en paz.\n\n"
            "#SantiagoDelEstero #ElPolaco #ProteccionAnimal #AhoraNoticias"
        )


def main():
    logger.info("=== Flyer El Polaco → Instagram ===")

    # 1. Buscar imagen
    img_url = _buscar_imagen_og()
    if not img_url:
        logger.error("No se encontró imagen válida en ninguna fuente. Abortando.")
        return

    # 2. Generar caption con Gemini
    caption = _generar_caption_gemini()
    logger.info(f"\n--- CAPTION ---\n{caption}\n---------------\n")

    # 3. Generar flyer con PIL
    flyer_path = None
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
        logger.info(f"✓ Flyer generado: {flyer_path}")
    except Exception as e:
        logger.error(f"Error generando flyer: {e}")
        return

    # 4. Subir flyer a WordPress para obtener URL pública
    flyer_url = None
    try:
        from datetime import datetime
        result = wordpress.upload_image(
            flyer_path,
            f"flyer-polaco-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
        )
        # upload_image puede retornar (id, url) o solo id según versión
        if isinstance(result, tuple):
            _, flyer_url = result
        else:
            # Buscar URL del media recién subido
            flyer_url = None  # se maneja abajo
            media_id = result
    except Exception as e:
        logger.error(f"Error subiendo flyer a WP: {e}")
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

    if not flyer_url:
        logger.error("No se obtuvo URL pública del flyer. Abortando publicación en Instagram.")
        return

    logger.info(f"✓ Flyer en WP: {flyer_url[:80]}")

    # 5. Publicar en Instagram
    ig_id = instagram.post_image(
        image_path=None,
        caption=caption,
        public_image_url=flyer_url,
    )

    if ig_id:
        logger.info(f"✓ Instagram publicado: ID={ig_id}")
    else:
        logger.error("✗ Instagram falló")


if __name__ == "__main__":
    main()
