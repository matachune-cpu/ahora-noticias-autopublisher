# -*- coding: utf-8 -*-
"""Prueba: publica en FB e IG el post de arboles - link post estandar"""
import requests, tempfile, os, sys
from dotenv import dotenv_values
import config
from flyer_generator import generate_flyer
from publishers import wordpress, instagram

env = dotenv_values(".env")
TOKEN = env["META_ACCESS_TOKEN"]
PAGE  = env["FB_PAGE_ID"]

WP_URL = "https://ahoranoticias.com.ar/60-000-arboles-por-ano-el-plan-que-podria-cambiarle-la-cara-a-santiago-del-estero/"
TITULO = "60.000 arboles por anno: el plan que podria cambiarle la cara a Santiago del Estero"
TITULO_DISPLAY = "60.000 árboles por año: el plan que podría cambiarle la cara a Santiago del Estero"

# Facebook - link post estandar
msg = "Leer la nota completa en nuestro sitio"
fb_msg = "60.000 arboles por anno para Santiago del Estero\n\nLee la nota completa en nuestro sitio"

print("Publicando en Facebook (link post)...")
r = requests.post(
    "https://graph.facebook.com/v19.0/{}/feed".format(PAGE),
    data={"message": "60.000 árboles por año para Santiago del Estero\n\nLeé la nota completa en nuestro sitio \U0001f447", "link": WP_URL, "access_token": TOKEN},
    timeout=30
)
if r.ok:
    fb_id = r.json().get("id")
    print("Facebook OK - ID: {}".format(fb_id))
else:
    print("Facebook error: {}".format(r.text[:200]))
    fb_id = None

# Instagram - flyer con plantilla
IG_CAPTION = (
    "\U0001f333 Santiago del Estero se viste de verde! \U0001f33f\n\n"
    "El ambicioso plan de forestar 60.000 árboles por año podría "
    "transformar el paisaje y el clima de nuestra provincia.\n\n"
    "¿Vos qué pensás? \U0001f447\n\n"
    "#SantiagoDelEstero #MedioAmbiente #Forestación #AhoraNoticias #Sustentabilidad"
)

print("Publicando en Instagram (flyer)...")
flyer_path = None
try:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        flyer_path = tmp.name
    generate_flyer(
        title="60.000 árboles por año: el plan que podría cambiarle la cara a Santiago del Estero",
        source_name="Santiago Ciudad",
        article_image_url=None,
        template_path=config.FLYER_TEMPLATE_PATH,
        output_path=flyer_path,
        categoria="Medioambiente",
    )
    _, flyer_url = wordpress.upload_image(image_path=flyer_path, filename="flyer-arboles-santiago.jpg")
    print("Flyer subido: {}".format(flyer_url))
    ig_id = instagram.post_image(image_path=None, caption=IG_CAPTION, public_image_url=flyer_url)
    print("Instagram OK - ID: {}".format(ig_id))
except Exception as e:
    print("Instagram error: {}".format(e))
    import traceback; traceback.print_exc()
finally:
    if flyer_path and os.path.exists(flyer_path):
        try: os.unlink(flyer_path)
        except: pass
