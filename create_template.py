"""
Crea una plantilla base para el flyer de Instagram.
Ejecutar una sola vez: python create_template.py
Después podés reemplazar templates/flyer_base.png con tu diseño real.
"""
from PIL import Image, ImageDraw, ImageFont
import os

os.makedirs("templates", exist_ok=True)

# Fondo degradado azul oscuro → azul medio
img = Image.new("RGB", (1080, 1080), (15, 45, 100))
draw = ImageDraw.Draw(img)

# Banda superior con color de acento
draw.rectangle([(0, 0), (1080, 120)], fill=(220, 30, 50))  # Rojo acento

# Banda inferior
draw.rectangle([(0, 960), (1080, 1080)], fill=(220, 30, 50))

# Logo placeholder (texto centrado)
try:
    font_logo = ImageFont.truetype("C:/Windows/Fonts/arialbd.ttf", 60)
    font_sub = ImageFont.truetype("C:/Windows/Fonts/arial.ttf", 28)
except Exception:
    font_logo = ImageFont.load_default()
    font_sub = ImageFont.load_default()

# Texto del medio (personalizar con tu nombre)
draw.text((540, 50), "TU MEDIO", font=font_logo, fill="white", anchor="mm")
draw.text((540, 1020), "www.tumedio.com.ar", font=font_sub, fill="white", anchor="mm")

img.save("templates/flyer_base.png", "PNG")
print("✓ Plantilla creada en templates/flyer_base.png")
print("  Reemplazala con tu diseño real manteniendo el tamaño 1080x1080 px.")
