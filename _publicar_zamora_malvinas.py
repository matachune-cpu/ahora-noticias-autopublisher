"""
Publica la nota sobre Zamora apoyando a Milei en la causa Malvinas.
Genera flyer con foto compuesta (jugadores Malvinas + Zamora + Milei),
publica en WordPress con sticky y luego en Instagram y Facebook.
"""
import logging
import os
import tempfile
from datetime import datetime
from io import BytesIO

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from PIL import Image, ImageDraw, ImageFont

load_dotenv()

import config
import database
from publishers import wordpress, instagram, facebook

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("zamora_malvinas")

# ── CONSTANTES ────────────────────────────────────────────────────────────────

TITULO_WP = (
    "'Ninguna especulación electoral por encima': Zamora apoyó a Milei "
    "en la causa Malvinas y pidió unidad nacional"
)

TITULO_FLYER = "Zamora respaldó a Milei en la causa Malvinas: 'Es una causa sagrada'"

CATEGORIA = "Política"

URL_CANONICA = "https://www.instagram.com/p/Dc2SAdnJ7W5/"
FUENTE = "Redes sociales / Gobierno de Santiago del Estero"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")

CUERPO_HTML = """
<p>El gobernador de Santiago del Estero, Gerardo Zamora, sorprendió este jueves al
respaldar públicamente la cadena nacional del presidente Javier Milei sobre la causa
Malvinas, llamando a la unidad de todos los argentinos por encima de cualquier
diferencia política o electoral.</p>

<p>En un mensaje publicado en sus redes sociales, el mandatario provincial afirmó que
"es muy valioso el cambio de posición del Gobierno nacional respecto a nuestras Islas
Malvinas" y que "esto permite que podamos estar todos los argentinos de acuerdo:
las Islas Malvinas nos pertenecen".</p>

<h2>El apoyo a la estrategia diplomática y el bloqueo petrolero</h2>

<p>Zamora manifestó su acuerdo con la decisión de fortalecer la presencia argentina en
la zona del Atlántico Sur y antártica, y con que se lleve adelante "una firme estrategia
diplomática y jurídica internacional, junto a todas las acciones necesarias para ejercer
nuestro derecho".</p>

<p>El gobernador destacó especialmente un punto de relevancia geopolítica: "Es de suma
importancia que el gobierno nacional haya decidido aplicar con firmeza todas las acciones
al alcance para no permitir la explotación ilegítima de nuestros recursos naturales, y
con ello impedir, por ejemplo, que se avance en la exploración petrolera de una empresa
de Israel, junto a Gran Bretaña".</p>

<h2>El llamado que sorprendió: 'frente institucional y político de todos los argentinos'</h2>

<p>El punto más llamativo del mensaje fue el llamado explícito a la unidad más allá de
las diferencias partidarias: "Estoy absolutamente de acuerdo en que ningún interés
subalterno, diferencia política o especulación electoral puede estar por encima de una
causa sagrada para los intereses de nuestra nación. La causa Malvinas es indudablemente
una de ellas, y por ello debemos estar unidos en un frente institucional y político todos
los argentinos, para defender nuestra soberanía".</p>

<p>El gobernador cerró su mensaje con la frase: "Las Malvinas son Argentinas!!!"</p>

<h2>El contexto: la cadena nacional de Milei</h2>

<p>Las palabras de Zamora llegaron en respuesta a una alocución presidencial de Milei en
cadena nacional, en la que el mandatario nacional anunció una postura firme sobre la
soberanía argentina de las Islas Malvinas e impulsó medidas para bloquear la exploración
petrolera de empresas extranjeras en aguas que Argentina reclama como propias.</p>

<p>El respaldo de Zamora —referente del peronismo santiagueño— fue recibido con sorpresa
en la escena política nacional y refuerza la idea de que la causa Malvinas genera
consenso transversal por encima de las diferencias partidarias.</p>
"""

# ── FUENTES DE IMÁGENES ───────────────────────────────────────────────────────

# Imagen de Zamora (busca en fuentes locales y nacionales)
FUENTES_ZAMORA = [
    "https://www.elliberal.com.ar/nota/politica/",  # buscará og:image de artículos recientes
    "https://www.nuevodiarioweb.com.ar/nota/politica/",
    "https://www.sde.gob.ar/noticias/",
    "https://www.infobae.com/santiago-del-estero/",
]
FUENTES_ZAMORA_DIRECTAS = [
    "https://www.elliberal.com.ar",
    "https://www.nuevodiarioweb.com.ar",
]

# Imagen de Milei (busca en fuentes nacionales)
FUENTES_MILEI = [
    "https://www.infobae.com/politica/",
    "https://www.tn.com.ar/politica/",
    "https://www.lanacion.com.ar/politica/",
    "https://www.clarin.com/politica/",
]

# Imagen Malvinas (foto jugadores con bandera - asset local o búsqueda)
MALVINAS_LOCAL_PATH = "assets/malvinas_copa2021.jpg"
FUENTES_MALVINAS = [
    "https://www.tycsports.com/futbol/seleccion-argentina/copa-america-2021-argentina-campeona-festejo-las-malvinas-son-argentinas-id383459.html",
    "https://www.tn.com.ar/deportes/",
]


# ── BÚSQUEDA DE IMÁGENES ──────────────────────────────────────────────────────

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
        logger.debug(f"og:image error {url}: {e}")
    return None


def _buscar_imagen_persona(keyword: str, fuentes: list[str]) -> str | None:
    """Busca la primera imagen válida de la persona en las fuentes dadas."""
    for base_url in fuentes:
        try:
            resp = requests.get(base_url, headers=HEADERS, timeout=10)
            if resp.status_code != 200:
                continue
            soup = BeautifulSoup(resp.text, "html.parser")
            # Buscar links de artículos que mencionen la keyword
            links = soup.find_all("a", href=True)
            for link in links:
                href = link["href"]
                text = link.get_text(strip=True).lower()
                if keyword.lower() in text or keyword.lower() in href.lower():
                    if not href.startswith("http"):
                        from urllib.parse import urlparse
                        parsed = urlparse(base_url)
                        href = f"{parsed.scheme}://{parsed.netloc}{href}"
                    img = _buscar_og_image(href)
                    if img:
                        logger.info(f"  Imagen {keyword}: {img[:80]}")
                        return img
        except Exception as e:
            logger.debug(f"Búsqueda {keyword} en {base_url}: {e}")
    return None


def _fetch_pil_image(url: str | None, local_path: str | None = None) -> Image.Image | None:
    if local_path and os.path.exists(local_path):
        try:
            return Image.open(local_path).convert("RGB")
        except Exception:
            pass
    if url:
        try:
            resp = requests.get(url, headers=HEADERS, timeout=12)
            return Image.open(BytesIO(resp.content)).convert("RGB")
        except Exception as e:
            logger.warning(f"No se pudo cargar imagen: {e}")
    return None


# ── GENERACIÓN DEL FLYER COMPUESTO ────────────────────────────────────────────

FLYER_W, FLYER_H = 1080, 1350
PHOTO_H = int(FLYER_H * 0.57)          # ~770px
RED_LINE_H = 12
TEXT_TOP = PHOTO_H + RED_LINE_H
LOGO_ZONE_H = 180
TITLE_ZONE_BOT = FLYER_H - LOGO_ZONE_H
RED_COLOR = (220, 30, 40)
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)
FONT_BOLD = "templates/fonts/OpenSans-Bold.ttf"
LOGO_PATH = "Perfil Facebook - Ahora Noticias.png"


def _get_font(size: int) -> ImageFont.FreeTypeFont:
    if os.path.exists(FONT_BOLD):
        try:
            return ImageFont.truetype(FONT_BOLD, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _fit_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    src_w, src_h = img.size
    ratio = max(w / src_w, h / src_h)
    new_w, new_h = int(src_w * ratio), int(src_h * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def _draw_label(draw: ImageDraw.ImageDraw, text: str, x: int, y: int, font: ImageFont.FreeTypeFont):
    """Dibuja etiqueta con fondo semitransparente oscuro."""
    bbox = draw.textbbox((0, 0), text, font=font)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad = 10
    draw.rectangle([(x, y), (x + tw + pad * 2, y + th + pad * 2)], fill=(0, 0, 0, 180))
    draw.text((x + pad, y + pad), text, font=font, fill=WHITE)


def generate_composite_flyer(
    malvinas_img: Image.Image | None,
    zamora_img: Image.Image | None,
    milei_img: Image.Image | None,
    title: str,
    output_path: str,
):
    if malvinas_img is None and zamora_img is None and milei_img is None:
        raise ValueError("Se necesita al menos una imagen para generar el flyer")

    canvas = Image.new("RGB", (FLYER_W, FLYER_H), WHITE)
    draw = ImageDraw.Draw(canvas)
    font_label = _get_font(30)

    # ── ZONA DE FOTOS ─────────────────────────────────────────────────
    available = [x for x in [malvinas_img, zamora_img, milei_img] if x is not None]

    if malvinas_img and (zamora_img or milei_img):
        # Diseño triptych: Malvinas arriba (60%), personas abajo (40%)
        top_h = int(PHOTO_H * 0.62)
        bot_h = PHOTO_H - top_h

        # Franja Malvinas
        m_crop = _fit_crop(malvinas_img, FLYER_W, top_h)
        canvas.paste(m_crop, (0, 0))

        # Franja personas
        personas = [x for x in [zamora_img, milei_img] if x is not None]
        nombres = []
        if zamora_img:
            nombres.append(("ZAMORA", zamora_img))
        if milei_img:
            nombres.append(("MILEI", milei_img))

        pw = FLYER_W // len(personas)
        for i, (nombre, pimg) in enumerate(nombres):
            crop = _fit_crop(pimg, pw, bot_h)
            canvas.paste(crop, (i * pw, top_h))
            # Etiqueta de nombre
            _draw_label(draw, nombre, i * pw + 12, top_h + 8, font_label)

        # Línea separadora vertical entre personas
        if len(personas) > 1:
            draw.rectangle([(FLYER_W // 2 - 2, top_h), (FLYER_W // 2 + 2, PHOTO_H)],
                           fill=WHITE)
        # Línea separadora horizontal Malvinas / personas
        draw.rectangle([(0, top_h - 3), (FLYER_W, top_h + 3)], fill=RED_COLOR)

    elif zamora_img and milei_img:
        # Solo personas: mitad y mitad
        pw = FLYER_W // 2
        z_crop = _fit_crop(zamora_img, pw, PHOTO_H)
        m_crop = _fit_crop(milei_img, pw, PHOTO_H)
        canvas.paste(z_crop, (0, 0))
        canvas.paste(m_crop, (pw, 0))
        _draw_label(draw, "ZAMORA", 12, 12, font_label)
        _draw_label(draw, "MILEI", pw + 12, 12, font_label)
        draw.rectangle([(pw - 2, 0), (pw + 2, PHOTO_H)], fill=WHITE)

    elif len(available) == 1:
        crop = _fit_crop(available[0], FLYER_W, PHOTO_H)
        canvas.paste(crop, (0, 0))

    # ── LÍNEA ROJA SEPARADORA ─────────────────────────────────────────
    draw.rectangle([(0, PHOTO_H), (FLYER_W, PHOTO_H + RED_LINE_H)], fill=RED_COLOR)

    # ── BADGE CATEGORÍA ───────────────────────────────────────────────
    badge_font = _get_font(30)
    label = CATEGORIA.upper()
    bbox = draw.textbbox((0, 0), label, font=badge_font)
    pad_x, pad_y = 28, 14
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pill_w = tw + pad_x * 2
    pill_h = th + pad_y * 2
    bx, by = 48, 48
    draw.rounded_rectangle([(bx, by), (bx + pill_w, by + pill_h)],
                            radius=pill_h // 2, fill=RED_COLOR)
    draw.text((bx + pad_x - bbox[0], by + (pill_h - th) // 2 - bbox[1]),
              label, font=badge_font, fill=WHITE)

    # ── TÍTULO ────────────────────────────────────────────────────────
    font = _get_font(46)
    title_upper = title.upper()
    max_w = FLYER_W - 55 * 2

    # wrap
    words = title_upper.split()
    lines, current = [], ""
    for word in words:
        test = f"{current} {word}".strip()
        if draw.textbbox((0, 0), test, font=font)[2] > max_w and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)
    lines = lines[:5]

    line_h = 46 + 14
    total_h = len(lines) * line_h - 14
    zone_h = TITLE_ZONE_BOT - TEXT_TOP
    y = TEXT_TOP + (zone_h - total_h) // 2

    for line in lines:
        tw = draw.textbbox((0, 0), line, font=font)[2]
        x = (FLYER_W - tw) // 2
        draw.text((x, y), line, font=font, fill=BLACK, stroke_width=1, stroke_fill=BLACK)
        y += line_h

    # ── LOGO ──────────────────────────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            lh = 185
            lw = int(logo.width * lh / logo.height)
            logo = logo.resize((lw, lh), Image.LANCZOS)
            canvas.paste(logo, ((FLYER_W - lw) // 2, TITLE_ZONE_BOT + (LOGO_ZONE_H - lh) // 2), logo)
        except Exception as e:
            logger.warning(f"Logo error: {e}")

    canvas.save(output_path, "JPEG", quality=94)
    logger.info(f"Flyer guardado: {output_path}")


# ── CAPTIONS GEMINI ───────────────────────────────────────────────────────────

def _generar_captions_gemini(wp_link: str) -> dict:
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")
        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            "Generá DOS textos para la siguiente nota política de alto impacto:\n\n"
            "TITULAR: 'Zamora apoyó categóricamente a Milei en la cadena nacional sobre Malvinas'\n\n"
            "CONTEXTO: El gobernador peronista Gerardo Zamora (Santiago del Estero) publicó un mensaje "
            "respaldando al presidente Milei luego de su cadena nacional sobre la causa Malvinas. "
            "Zamora acordó con la postura de fortalecer la presencia argentina en el Atlántico Sur, "
            "bloquear la exploración petrolera de una empresa israelí junto a Gran Bretaña, y "
            "llevar adelante una firme estrategia diplomática internacional. Lo más llamativo: "
            "pidió 'un frente institucional y político de todos los argentinos' diciendo que "
            "'ningún interés subalterno, diferencia política o especulación electoral puede estar "
            "por encima de una causa sagrada'. Cerró con 'Las Malvinas son Argentinas!!!'.\n\n"
            "TEXTO 1 — Caption Instagram (máx 160 palabras):\n"
            "- Hook que transmita sorpresa genuina por el gesto de unidad\n"
            "- Tono: impactante, informativo, sin editorial política\n"
            "- Emojis estratégicos (🇦🇷🏝️)\n"
            "- Cerrá con: #SantiagoDelEstero #Malvinas #AhoraNoticias #Política\n\n"
            "TEXTO 2 — Copy Facebook (máx 80 palabras):\n"
            "- Arranca con el dato más sorprendente\n"
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
            "🇦🇷 SORPRESA EN LA POLÍTICA ARGENTINA\n\n"
            "El gobernador peronista Gerardo Zamora (Santiago del Estero) respaldó "
            "categóricamente al presidente Milei en la cadena nacional sobre la causa Malvinas.\n\n"
            "🏝️ Apoyó el bloqueo a la exploración petrolera de empresas extranjeras.\n"
            "🤝 Llamó a 'un frente institucional y político de todos los argentinos'.\n"
            "💬 'Ninguna especulación electoral puede estar por encima de una causa sagrada'.\n\n"
            "Las Malvinas generan consenso por encima de la grieta.\n\n"
            "#SantiagoDelEstero #Malvinas #AhoraNoticias #Política"
        )
        fb = (
            "🇦🇷 ZAMORA RESPALDÓ A MILEI en la cadena nacional sobre Malvinas: "
            "'Ninguna diferencia política puede estar por encima de una causa sagrada'. "
            "El gobernador peronista pidió un 'frente institucional y político de todos los argentinos' "
            "y apoyó el bloqueo a la exploración petrolera de empresas extranjeras.\n\n"
            f"Leé la nota completa → {wp_link}"
        )
        return {"instagram": ig, "facebook": fb}


# ── MAIN ──────────────────────────────────────────────────────────────────────

def main():
    database.init_db()

    if database.is_published(URL_CANONICA):
        logger.warning("Esta nota ya fue publicada. Abortando.")
        return

    logger.info("=== Publicando: Zamora apoya a Milei en Malvinas ===")

    # ── BUSCAR IMÁGENES ──────────────────────────────────────────────────────
    logger.info("Buscando imagen de Zamora...")
    img_zamora_url = _buscar_imagen_persona("zamora", FUENTES_ZAMORA_DIRECTAS)
    if not img_zamora_url:
        for url in FUENTES_ZAMORA:
            img_zamora_url = _buscar_og_image(url)
            if img_zamora_url:
                break

    logger.info("Buscando imagen de Milei...")
    img_milei_url = None
    for url in FUENTES_MILEI:
        img_milei_url = _buscar_og_image(url)
        if img_milei_url:
            break

    logger.info("Cargando imagen Malvinas (asset local)...")
    malvinas_pil = _fetch_pil_image(None, local_path=MALVINAS_LOCAL_PATH)
    if not malvinas_pil:
        logger.info("Asset local no disponible, buscando en línea...")
        for url in FUENTES_MALVINAS:
            mv_url = _buscar_og_image(url)
            if mv_url:
                malvinas_pil = _fetch_pil_image(mv_url)
                break

    zamora_pil = _fetch_pil_image(img_zamora_url)
    milei_pil = _fetch_pil_image(img_milei_url)

    logger.info(f"  Malvinas: {'OK' if malvinas_pil else 'no disponible'}")
    logger.info(f"  Zamora:   {'OK' if zamora_pil else 'no disponible'}")
    logger.info(f"  Milei:    {'OK' if milei_pil else 'no disponible'}")

    if not any([malvinas_pil, zamora_pil, milei_pil]):
        logger.error("Sin ninguna imagen. Abortando.")
        return

    # ── PUBLICAR EN WORDPRESS ────────────────────────────────────────────────
    # Imagen destacada de WP: primera disponible
    wp_img_url = img_zamora_url or img_milei_url
    wp_img_id = None
    if wp_img_url:
        try:
            result = wordpress.upload_image(image_url=wp_img_url,
                                            filename=f"zamora-malvinas-{datetime.now().strftime('%Y%m%d')}.jpg")
            if isinstance(result, tuple):
                wp_img_id, _ = result
        except Exception as e:
            logger.warning(f"Imagen WP fallida: {e}")

    cat_ids = []
    for cat in ["Política", "Santiago del Estero"]:
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
        logger.error("WP no devolvió respuesta.")
        return

    if isinstance(wp_result, tuple):
        wp_id, wp_link = wp_result
    else:
        wp_id = wp_result.get("id") if isinstance(wp_result, dict) else None
        wp_link = wp_result.get("link", "") if isinstance(wp_result, dict) else ""

    logger.info(f"✓ WordPress: ID={wp_id} | {wp_link}")

    # Rotar sticky
    if wp_id:
        try:
            wordpress.rotate_sticky_posts(new_post_ids=[int(wp_id)], max_sticky=4)
            logger.info("✓ Sticky rotation OK")
        except Exception as e:
            logger.warning(f"Rotate sticky error: {e}")

    database.mark_published(URL_CANONICA, TITULO_WP, FUENTE,
                            wp_post_id=str(wp_id) if wp_id else None)

    # ── GENERAR FLYER ────────────────────────────────────────────────────────
    flyer_path = None
    flyer_url = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name

        generate_composite_flyer(
            malvinas_img=malvinas_pil,
            zamora_img=zamora_pil,
            milei_img=milei_pil,
            title=TITULO_FLYER,
            output_path=flyer_path,
        )
        logger.info("✓ Flyer generado")

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        upload_result = wordpress.upload_image(flyer_path, f"flyer-zamora-malvinas-{ts}.jpg")
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
        logger.error("Sin URL pública del flyer. Abortando redes sociales.")
        return

    # ── CAPTIONS ─────────────────────────────────────────────────────────────
    captions = _generar_captions_gemini(wp_link or "https://ahoranoticias.com.ar")
    logger.info(f"\n--- INSTAGRAM ---\n{captions['instagram']}\n")
    logger.info(f"--- FACEBOOK ---\n{captions['facebook']}\n")

    # ── INSTAGRAM ────────────────────────────────────────────────────────────
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

    # ── FACEBOOK ─────────────────────────────────────────────────────────────
    fb_id = None
    try:
        fb_id = facebook.post_link(
            title=TITULO_WP,
            wp_post_url=wp_link or "https://ahoranoticias.com.ar",
            original_url=wp_link or "https://ahoranoticias.com.ar",
            image_url=flyer_url,
            caption=captions["facebook"],
        )
        logger.info(f"✓ Facebook: {'ID=' + str(fb_id) if fb_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Facebook: {e}")

    logger.info(f"\n{'━'*55}")
    logger.info(f"  WP:  {wp_link}")
    logger.info(f"  IG:  {ig_id or 'falló'}")
    logger.info(f"  FB:  {fb_id or 'falló'}")
    logger.info(f"{'━'*55}")


if __name__ == "__main__":
    main()
