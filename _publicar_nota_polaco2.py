"""
Publicación: continuación de la nota de El Polaco Riemersma.
Ángulo: posteo viral que revela que vivía amenazado.
Publica en WordPress + genera flyer con Gemini caption + publica Instagram + Facebook.
"""
import base64
import io
import logging
import os
import tempfile
import time
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
logger = logging.getLogger("polaco2")

# ── DATOS ────────────────────────────────────────────────────────────────────

TITULO = (
    "Le prendieron fuego al predio y tenía el refugio blindado con cámaras: "
    "revelan que El Polaco vivía amenazado antes de morir"
)

TITULO_FLYER = (
    "'No vivía perseguido: vivía amenazado' — la revelación que sacude Santiago del Estero"
)

CATEGORIA_FLYER = "Santiago del Estero"

URL_CANONICA = "https://www.facebook.com/share/19X8yCsn2X/"  # fuente del posteo viral

FUENTE = "Redes sociales / Ahora Noticias"

CUERPO_HTML = """
<p><strong>Un posteo que se volvió viral en cuestión de horas en Santiago del Estero está
poniendo en duda la narrativa del "accidente" y obligando a repasar los últimos meses de
vida de Eduardo "El Polaco" Groh Riemersma desde otro ángulo: el de alguien que vivía
bajo amenaza permanente.</strong></p>

<p>La publicación, compartida más de <strong>1.100 veces</strong> y con más de
<strong>5.300 reacciones</strong> y <strong>1.200 comentarios</strong> en pocas horas,
fue escrita por alguien que dice conocer a Eduardo personalmente y que tiene formación
en "conciencia situacional". El autor pide que no se mire solo el accidente: pide que
se mire el entorno completo en el que El Polaco desarrollaba su trabajo.</p>

<h2>El blindaje que nadie entendía</h2>

<p>Según el posteo, El Montecito de los Canichones —el refugio que Eduardo fundó y donde
convivían más de 400 perros— contaba con un <strong>sistema pesado de iluminación
perimetral y cámaras de seguridad</strong> que no tenían ningún sentido operativo para
cuidar animales: los perros no se peleaban entre sí, el manejo de la jauría era, según
quienes lo frecuentaban, impecable.</p>

<p>"Ese blindaje tenía un solo objetivo: seguridad personal, disuasión y respaldo ante
las amenazas que sufría", sostiene el texto que circula en redes.</p>

<h2>"Al Pola ya le habían prendido fuego"</h2>

<p>Uno de los párrafos más explosivos del posteo revela que alguien intentó incendiar el
predio: <em>"Al Pola ya le habían prendido fuego cerca del predio"</em>. El episodio,
que no había trascendido públicamente hasta ahora, sería una de las razones por las que
Eduardo habría reforzado la seguridad del refugio.</p>

<p>El autor agrega que Riemersma <strong>"se metió directamente con denuncias complicadas"</strong>
y que <strong>"se guardó cosas gravísimas hasta el último día de su vida por pura
protección"</strong>. La frase más lapidaria del texto: <em>"Cuando tocás ciertos intereses
en el monte, la única garantía de prueba y defensa ante un amedrentamiento o un ataque
directo es el registro fílmico constante"</em>.</p>

<h2>"Vivía amenazado, no perseguido"</h2>

<p>El posteo cierra con una distinción que sus seguidores consideran clave:
<em>"El Polaco no vivía perseguido: vivía amenazado"</em>. La diferencia no es semántica:
implica que existían actores concretos, con intereses concretos, que lo presionaban.</p>

<p>"Hay cosas que no se dicen por respeto, pero que se leen clarísimo en el terreno",
concluye el texto, exigiendo que el foco no esté únicamente en el cuidado de los
animales del refugio, sino también en esclarecer qué peligros rodeaban a Eduardo.</p>

<h2>El accidente que sigue bajo investigación</h2>

<p>La fiscalía provincial, a cargo del fiscal Martín Silva, ya había ordenado la revisión
de las cámaras de seguridad de la zona donde ocurrió el accidente —la intersección de
avenida Alsina y Ramón Gómez Cornet— para determinar con exactitud la mecánica del
siniestro. Hasta el momento no hay ninguna hipótesis oficial que descarte o confirme la
versión de un accidente.</p>

<p>Lo que sí es un hecho es que este posteo abrió una conversación que no estaba en la
agenda pública: si la muerte de El Polaco fue un accidente aislado, o el punto final
de una historia mucho más oscura.</p>

<hr>

<p><em>Esta nota se basa en un posteo viral de acceso público en redes sociales.
Ahora Noticias no formula acusaciones: reproduc e lo que circula en el debate público
santiagueño y señala que existe una investigación fiscal en curso. Cualquier persona
con información puede comunicarse con la fiscalía provincial.</em></p>
"""

# Fuentes de imagen para El Polaco (las mismas que la nota anterior)
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

_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")


def _buscar_imagen_og() -> str | None:
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
                        logger.info(f"Imagen: {img[:80]}")
                        return img
        except Exception as e:
            logger.debug(f"Error en {url}: {e}")
    return None


def _generar_captions_gemini(wp_post_url: str) -> dict:
    """Genera captions para Instagram y Facebook con Gemini."""
    try:
        from google import genai

        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")

        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            "Generá DOS textos separados para la siguiente nota de continuación sobre El Polaco Riemersma:\n\n"
            "TITULAR: 'Le prendieron fuego al predio y tenía el refugio blindado con cámaras: "
            "revelan que El Polaco vivía amenazado antes de morir'\n\n"
            "CONTEXTO: Un posteo viral con 5.300 reacciones, 1.200 comentarios y 1.100 compartidos "
            "revela que Eduardo 'El Polaco' Riemersma —el proteccionista que murió el jueves al "
            "esquivar un perro en su moto— vivía bajo amenaza constante: tenía el refugio blindado "
            "con iluminación perimetral y cámaras de seguridad (no para los perros, sino para su "
            "seguridad personal), alguien le había prendido fuego cerca del predio, hacía denuncias "
            "peligrosas y guardaba información comprometedora. La frase más impactante del posteo: "
            "'El Polaco no vivía perseguido: vivía amenazado.'\n\n"
            "TEXTO 1 — Caption para Instagram (máx 200 palabras):\n"
            "- Hook impactante que detenga el scroll\n"
            "- Tono: grave, respetuoso, periodístico. Esto es serio.\n"
            "- Usá emojis con criterio\n"
            "- Cerrá con: #SantiagoDelEstero #ElPolaco #AhoraNoticias #JusticiaParaElPolaco\n\n"
            "TEXTO 2 — Copy para Facebook (máx 120 palabras):\n"
            "- Directo, informativo, con gancho al principio\n"
            "- Cerrá con: 'Leé la nota completa →' (sin URL, la ponemos nosotros)\n"
            "- Sin hashtags en Facebook\n\n"
            "Respondé EXACTAMENTE así, sin texto adicional:\n"
            "===INSTAGRAM===\n"
            "[caption instagram]\n"
            "===FACEBOOK===\n"
            "[copy facebook]\n"
        )

        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        raw = response.text.strip()

        ig_caption = ""
        fb_copy = ""
        if "===INSTAGRAM===" in raw and "===FACEBOOK===" in raw:
            parts = raw.split("===FACEBOOK===")
            ig_part = parts[0].replace("===INSTAGRAM===", "").strip()
            fb_part = parts[1].strip()
            ig_caption = ig_part
            fb_copy = fb_part
        else:
            ig_caption = raw
            fb_copy = raw[:300]

        logger.info(f"Captions Gemini generados (IG: {len(ig_caption)}c / FB: {len(fb_copy)}c)")
        return {"instagram": ig_caption, "facebook": fb_copy}

    except Exception as e:
        logger.warning(f"Gemini no disponible: {e}. Usando captions de respaldo.")
        ig = (
            "🚨 Esto hay que leerlo con atención.\n\n"
            "Un posteo viral revela que Eduardo 'El Polaco' Riemersma —el hombre que murió "
            "esquivando a un perro— vivía bajo amenaza real.\n\n"
            "▪ Le habían prendido fuego al predio\n"
            "▪ Tenía el refugio blindado con cámaras (no para los perros)\n"
            "▪ Hacía denuncias peligrosas\n"
            "▪ Guardaba información comprometedora\n\n"
            "La frase que lo dice todo: 'No vivía perseguido. Vivía amenazado.'\n\n"
            "Más de 5.300 reacciones y 1.100 compartidos en pocas horas. Santiago exige respuestas.\n\n"
            "#SantiagoDelEstero #ElPolaco #AhoraNoticias #JusticiaParaElPolaco"
        )
        fb = (
            "🚨 Un posteo viral revela que El Polaco Riemersma vivía bajo amenaza: le habían "
            "prendido fuego al predio, tenía el refugio blindado con cámaras de seguridad personal "
            "y guardaba información comprometedora sobre 'ciertos intereses en el monte'.\n\n"
            "'No vivía perseguido: vivía amenazado.'\n\n"
            "Leé la nota completa →"
        )
        return {"instagram": ig, "facebook": fb}


def main():
    database.init_db()

    if database.is_seen(URL_CANONICA):
        logger.warning("Esta nota ya fue publicada. Abortando.")
        return

    logger.info("=== Publicando: El Polaco — ángulo amenazas ===")

    # 1. Imagen
    img_url = _buscar_imagen_og()
    img_id = None
    if img_url:
        try:
            img_id = wordpress.upload_image(img_url, TITULO)
            logger.info(f"✓ Imagen subida ID={img_id}")
        except Exception as e:
            logger.warning(f"Error imagen: {e}")

    # 2. Categorías
    cat_ids = []
    for cat_name in ["Santiago del Estero", "Seguridad"]:
        try:
            cid = wordpress.get_or_create_category(cat_name)
            if cid:
                cat_ids.append(cid)
        except Exception:
            pass

    # 3. Publicar en WordPress
    try:
        result = wordpress.create_post(
            title=TITULO,
            content=CUERPO_HTML,
            status="publish",
            featured_media=img_id,
            sticky=True,
            categories=cat_ids,
        )
    except Exception as e:
        logger.error(f"Error WP: {e}")
        return

    if not result or not result.get("id"):
        logger.error("WordPress no respondió.")
        return

    wp_id = result.get("id")
    wp_link = result.get("link", "")
    logger.info(f"✓ WordPress: ID={wp_id} | {wp_link}")

    try:
        wordpress.rotate_sticky_posts(max_sticky=4)
    except Exception:
        pass

    # 4. Generar captions con Gemini
    captions = _generar_captions_gemini(wp_link)
    logger.info(f"\n--- INSTAGRAM ---\n{captions['instagram']}\n")
    logger.info(f"--- FACEBOOK ---\n{captions['facebook']}\n")

    # 5. Generar flyer
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
        logger.info(f"✓ Flyer generado")

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        upload_result = wordpress.upload_image(flyer_path, f"flyer-polaco2-{ts}.jpg")
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

    # 6. Instagram
    ig_id = None
    if flyer_url:
        try:
            ig_id = instagram.post_image(
                image_path=None,
                caption=captions["instagram"],
                public_image_url=flyer_url,
            )
            logger.info(f"✓ Instagram: ID={ig_id}" if ig_id else "✗ Instagram falló")
        except Exception as e:
            logger.error(f"Error Instagram: {e}")
    else:
        logger.warning("Sin flyer URL — Instagram omitido")

    # 7. Facebook (link a ahoranoticias.com.ar, nunca a fuente original)
    fb_id = None
    try:
        fb_caption = f"{captions['facebook']}\n\n{wp_link}"
        fb_id = facebook.post_link(
            title=TITULO,
            wp_post_url=wp_link,
            original_url=URL_CANONICA,
            image_url=flyer_url or img_url,
            caption=fb_caption,
        )
        logger.info(f"✓ Facebook: ID={fb_id}" if fb_id else "✗ Facebook falló")
    except Exception as e:
        logger.error(f"Error Facebook: {e}")

    # 8. Registrar
    database.mark_seen(URL_CANONICA, TITULO, FUENTE)

    logger.info(f"\n{'━'*60}")
    logger.info("PUBLICADO COMPLETO")
    logger.info(f"  WP: {wp_link}")
    logger.info(f"  IG: {ig_id or 'falló'}")
    logger.info(f"  FB: {fb_id or 'falló'}")
    logger.info(f"{'━'*60}")


if __name__ == "__main__":
    main()
