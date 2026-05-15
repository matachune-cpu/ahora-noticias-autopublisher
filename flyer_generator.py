"""
Genera flyers para Instagram - Ahora Noticias
Dimensiones: 1080 x 1350 px
Diseño: foto arriba, línea roja, zona blanca con título en Open Sans Bold mayúsculas, logo al pie
"""
from PIL import Image, ImageDraw, ImageFont
import requests
import io
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

FLYER_W = 1080
FLYER_H = 1350
FLYER_SIZE = (FLYER_W, FLYER_H)

PHOTO_HEIGHT = int(FLYER_H * 0.57)        # ~770px foto
RED_LINE_H = 12
TEXT_AREA_TOP = PHOTO_HEIGHT + RED_LINE_H
LOGO_ZONE_H = 180                          # espacio reservado para el logo al pie
TITLE_ZONE_TOP = TEXT_AREA_TOP + 30
TITLE_ZONE_BOT = FLYER_H - LOGO_ZONE_H

RED_COLOR = (220, 30, 40)
WHITE = (255, 255, 255)
BLACK = (20, 20, 20)

FONT_BOLD = "templates/fonts/OpenSans-Bold.ttf"
LOGO_PATH = "Perfil Facebook - Ahora Noticias.png"
FONT_SIZE = 48
MARGIN = 55


def _get_font(size: int = FONT_SIZE) -> ImageFont.FreeTypeFont:
    if os.path.exists(FONT_BOLD):
        try:
            return ImageFont.truetype(FONT_BOLD, size)
        except Exception:
            pass
    # Fallback a fuente del sistema
    for path in ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/verdanab.ttf"]:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _fetch_photo(url: str) -> Optional[Image.Image]:
    try:
        resp = requests.get(url, timeout=12)
        return Image.open(io.BytesIO(resp.content)).convert("RGB")
    except Exception as e:
        logger.warning(f"No se pudo cargar foto: {e}")
        return None


def _fit_crop(img: Image.Image, w: int, h: int) -> Image.Image:
    """Escala y recorta centrado para llenar exactamente w×h."""
    src_w, src_h = img.size
    ratio = max(w / src_w, h / src_h)
    new_w, new_h = int(src_w * ratio), int(src_h * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    left = (new_w - w) // 2
    top = (new_h - h) // 2
    return img.crop((left, top, left + w, top + h))


def _wrap_title(text: str, font: ImageFont.FreeTypeFont, max_w: int, draw: ImageDraw.ImageDraw) -> list[str]:
    """
    Parte el texto en líneas que quepan en max_w.
    Respeta lectura natural: no corta palabras, y favorece
    líneas equilibradas (ninguna línea muy corta al final).
    """
    words = text.split()
    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_w and current:
            lines.append(current)
            current = word
        else:
            current = test
    if current:
        lines.append(current)

    # Si la última línea es muy corta (< 30% del ancho), redistribuir
    if len(lines) >= 2:
        last_bbox = draw.textbbox((0, 0), lines[-1], font=font)
        if last_bbox[2] < max_w * 0.30:
            # Unir últimas dos líneas y redistribuir
            combined = lines[-2] + " " + lines[-1]
            words_combined = combined.split()
            mid = len(words_combined) // 2
            line_a = " ".join(words_combined[:mid])
            line_b = " ".join(words_combined[mid:])
            lines = lines[:-2] + [line_a, line_b]

    return lines[:5]  # máximo 5 líneas


def _draw_category_badge(draw: ImageDraw.ImageDraw, label: str, font: ImageFont.FreeTypeFont):
    """Dibuja la etiqueta de categoría estilo píldora roja en el margen superior izquierdo."""
    if not label:
        return

    label_upper = label.upper()
    padding_x = 28
    padding_y = 14
    margin = 48     # margen desde el borde de la foto

    bbox = draw.textbbox((0, 0), label_upper, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]

    pill_w = text_w + padding_x * 2
    pill_h = text_h + padding_y * 2
    pill_x = margin
    pill_y = margin
    radius = pill_h // 2

    # Fondo rojo redondeado
    draw.rounded_rectangle(
        [(pill_x, pill_y), (pill_x + pill_w, pill_y + pill_h)],
        radius=radius,
        fill=RED_COLOR,
    )
    # Texto blanco centrado
    text_x = pill_x + padding_x
    text_y = pill_y + padding_y
    draw.text((text_x, text_y), label_upper, font=font, fill=WHITE)


def generate_flyer(
    title: str,
    source_name: str,
    article_image_url: Optional[str],
    template_path: str,
    output_path: str,
    categoria: str = "",
) -> str:

    canvas = Image.new("RGB", FLYER_SIZE, WHITE)

    # ── 1. FOTO SUPERIOR ──────────────────────────────────────────────
    photo = _fetch_photo(article_image_url) if article_image_url else None
    if photo:
        photo_crop = _fit_crop(photo, FLYER_W, PHOTO_HEIGHT)
    else:
        photo_crop = Image.new("RGB", (FLYER_W, PHOTO_HEIGHT), (70, 70, 70))
    canvas.paste(photo_crop, (0, 0))

    # ── 2. LÍNEA ROJA ─────────────────────────────────────────────────
    draw = ImageDraw.Draw(canvas)
    draw.rectangle([(0, PHOTO_HEIGHT), (FLYER_W, PHOTO_HEIGHT + RED_LINE_H)], fill=RED_COLOR)

    # ── 2b. ETIQUETA DE CATEGORÍA (sobre la foto, margen superior izq) ─
    if categoria:
        font_badge = _get_font(30)
        _draw_category_badge(draw, categoria, font_badge)

    # ── 3. TÍTULO EN MAYÚSCULAS ───────────────────────────────────────
    font = _get_font(FONT_SIZE)
    title_upper = title.upper()
    max_text_w = FLYER_W - MARGIN * 2

    lines = _wrap_title(title_upper, font, max_text_w, draw)

    line_spacing = 14
    line_h = FONT_SIZE + line_spacing
    total_text_h = len(lines) * line_h - line_spacing

    # Centrar verticalmente en la zona del título
    title_zone_h = TITLE_ZONE_BOT - TITLE_ZONE_TOP
    text_y = TITLE_ZONE_TOP + (title_zone_h - total_text_h) // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        text_w = bbox[2] - bbox[0]
        x = (FLYER_W - text_w) // 2          # centrado horizontal exacto
        draw.text((x, text_y), line, font=font, fill=BLACK,
                  stroke_width=1, stroke_fill=BLACK)
        text_y += line_h

    # ── 4. LOGO ───────────────────────────────────────────────────────
    if os.path.exists(LOGO_PATH):
        try:
            logo = Image.open(LOGO_PATH).convert("RGBA")
            logo_h = 185
            ratio = logo_h / logo.height
            logo_w = int(logo.width * ratio)
            logo = logo.resize((logo_w, logo_h), Image.LANCZOS)
            logo_x = (FLYER_W - logo_w) // 2
            logo_y = TITLE_ZONE_BOT + (LOGO_ZONE_H - logo_h) // 2
            canvas.paste(logo, (logo_x, logo_y), logo)
        except Exception as e:
            logger.warning(f"Error cargando logo: {e}")

    # ── 5. GUARDAR ────────────────────────────────────────────────────
    canvas.save(output_path, "JPEG", quality=94)
    logger.info(f"Flyer guardado: {output_path}")
    return output_path
