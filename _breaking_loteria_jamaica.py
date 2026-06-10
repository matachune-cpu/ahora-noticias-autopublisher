"""
VIRAL: Mujer gana lotería en Jamaica y cobra con máscara de emoji
Publica en WordPress, Facebook e Instagram (flyer con plantilla propia)
"""
import json, requests, base64, time, tempfile, os
from dotenv import dotenv_values
import database, config
from flyer_generator import generate_flyer
from publishers import wordpress, instagram

env = dotenv_values(".env")
TOKEN = env["META_ACCESS_TOKEN"]
PAGE  = env["FB_PAGE_ID"]

URL_ORIGINAL = "https://www.quepasajujuy.com.ar/gano-180-millones-y-fue-a-reclamarlos-con-una-mascara-para-que-su-familia-no-la-reconociera/"
SOURCE = "Viral"

TITULO = "😱 Ganó 180 millones en la lotería y fue a cobrarlos con una máscara de emoji para que su familia no la reconociera"

CUERPO_HTML = """<p>Una mujer en Jamaica se convirtió en el centro de atención mundial, pero no por el dinero que ganó, sino por la peculiar decisión que tomó a la hora de reclamar su premio. La ganadora del Super Lotto jamaicano se presentó ante las cámaras usando una máscara de emoji sonriente para ocultar completamente su identidad.</p>

<p>El motivo: evitar que familiares, amigos y conocidos supieran que ella era la afortunada ganadora de 180 millones de dólares jamaicanos, equivalentes a aproximadamente 1,4 millones de dólares estadounidenses. Las imágenes de la mujer posando con su cheque gigante —con una carita feliz en lugar de su rostro— recorrieron el mundo en pocas horas y desataron miles de reacciones en redes sociales.</p>

<p>Mientras algunos usuarios la criticaron por la extravagancia de la situación, la gran mayoría consideró que fue una decisión absolutamente inteligente. "Si gano la lotería hago lo mismo", escribió uno de los miles de internautas que comentaron la historia. Los expertos en psicología financiera no tardaron en señalar que el anonimato de los ganadores de premios millonarios es, de hecho, una recomendación habitual: evita pedidos de dinero, presiones familiares y hasta situaciones de riesgo para la seguridad personal.</p>

<p>La identidad de la ganadora solo se conoce parcialmente: el cheque que sostuvo frente a las cámaras lleva las iniciales N. Gray. El Super Lotto es uno de los juegos de azar más populares de Jamaica y este caso volvió a poner sobre la mesa el debate sobre el anonimato de los grandes ganadores. En algunos países está permitido cobrar bajo seudónimo; en otros, la ley exige que el ganador se identifique públicamente.</p>

<p>La historia de N. Gray se volvió viral en todo el mundo y se convirtió en un símbolo de la tensión que muchos enfrentan cuando llega la gran suerte: ¿cómo protegerse de los que llegan solo cuando hay dinero de por medio?</p>"""

IG_CAPTION = """😱💰 ¡Ganó 180 millones en la lotería y fue a cobrarlos con una máscara de emoji!

Una mujer en Jamaica no quería que su familia ni sus amigos supieran que había ganado el Super Lotto. Su solución: aparecer en público con una carita feliz tapándole la cara.

Y la verdad... ¿no es lo más inteligente del mundo? 😂🤣

¿Vos qué harías si ganás la lotería? 👇

#Lotería #Jamaica #Viral #AhoraNoticias #DineroInteligente"""

FB_MSG = """😱💰 GANÓ 180 MILLONES EN LA LOTERÍA Y FUE A COBRARLOS CON UNA MÁSCARA DE EMOJI

Una mujer jamaicana no quería que nadie de su entorno supiera que se había ganado el Super Lotto. Su solución fue tan simple como brillante: aparecer frente a las cámaras con una máscara de emoji sonriente tapándole la cara.

Las imágenes recorrieron el mundo y dividieron opiniones: ¿locura o jugada maestra? Para muchos expertos en finanzas personales, proteger la identidad tras un premio millonario es, en realidad, la decisión más inteligente que se puede tomar.

Leé la nota completa 👇"""

def wp_auth():
    t = base64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {t}"}

def upload_img_from_path(path, filename):
    try:
        with open(path, "rb") as f: data = f.read()
        h = {**wp_auth(), "Content-Disposition": f'attachment; filename="{filename}"', "Content-Type": "image/jpeg"}
        r = requests.post(f"{env['WP_URL'].rstrip('/')}/wp-json/wp/v2/media", headers=h, data=data, timeout=30)
        if r.ok: d = r.json(); return d.get("id"), d.get("source_url","")
    except Exception as e: print(f"  img error: {e}")
    return None, None

def post_wp(titulo, cuerpo, media_id=None):
    attr = f'<p><em>Fuente: información viral internacional</em></p>'
    p = {"title": titulo, "content": cuerpo + attr, "status": "publish"}
    if media_id: p["featured_media"] = media_id
    r = requests.post(f"{env['WP_URL'].rstrip('/')}/wp-json/wp/v2/posts",
        json=p, headers=wp_auth(), timeout=30)
    r.raise_for_status()
    d = r.json(); return str(d["id"]), d.get("link","")

def post_fb_con_imagen(wp_url, image_url=None):
    """Link post estándar — aparece en el feed principal (móvil y escritorio).
    Facebook scrapea la og:image del artículo de WordPress (Yoast SEO).
    NO usar attached_media ni /photos: esos crean photo posts que solo
    aparecen en la pestaña Fotos, no en el feed."""
    msg = f"{FB_MSG}\n{wp_url}"
    r = requests.post(f"https://graph.facebook.com/v19.0/{PAGE}/feed",
        data={"message": msg, "link": wp_url, "access_token": TOKEN}, timeout=30)
    return r.json().get("id") if r.ok else None

# ── Main ─────────────────────────────────────────────────────────────────────
database.init_db()
if database.is_published(URL_ORIGINAL):
    print("Ya publicado."); exit(0)

print("Publicando nota viral: lotería Jamaica con máscara emoji...")

# Buscar imagen limpia en la carpeta del proyecto
IMAGE_PATH = None
import glob
for pat in [r"C:\Users\USUARIO\Downloads\*loteria*", r"C:\Users\USUARIO\Downloads\*emoji*",
            r"C:\Users\USUARIO\Downloads\*jamaica*", r"C:\Users\USUARIO\Desktop\*loteria*",
            r"C:\Users\USUARIO\Desktop\*emoji*"]:
    found = glob.glob(pat, recursive=False)
    if found:
        IMAGE_PATH = found[0]
        print(f"  Imagen encontrada: {IMAGE_PATH}")
        break

media_id, media_url = None, None
if IMAGE_PATH:
    media_id, media_url = upload_img_from_path(IMAGE_PATH, "loteria-jamaica-emoji.jpg")

# WordPress
wp_id, wp_url = post_wp(TITULO, CUERPO_HTML, media_id)
print(f"  WP={wp_id} | {wp_url}")

# Facebook
fb_id = post_fb_con_imagen(wp_url, media_url)
print(f"  FB={'OK' if fb_id else 'error'}")

# Instagram — flyer con plantilla propia (sin referencias externas)
flyer_path = None
ig_ok = False
try:
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
        flyer_path = tmp.name
    generate_flyer(
        title="Ganó 180 millones en la lotería y cobró con una máscara de emoji para que su familia no la reconociera",
        source_name="Ahora Noticias",
        article_image_url=None,  # se reemplazará si hay imagen limpia
        template_path=config.FLYER_TEMPLATE_PATH,
        output_path=flyer_path,
        categoria="Sociedad",
    )
    _, flyer_public_url = wordpress.upload_image(image_path=flyer_path,
        filename="flyer-loteria-jamaica.jpg")
    ig_post_id = instagram.post_image(
        image_path=None, caption=IG_CAPTION, public_image_url=flyer_public_url)
    ig_ok = bool(ig_post_id)
    print(f"  IG={'OK ' + str(ig_post_id) if ig_ok else 'error'}")
except Exception as e:
    print(f"  IG error: {e}")
finally:
    if flyer_path and os.path.exists(flyer_path):
        try: os.unlink(flyer_path)
        except: pass

database.mark_published(url=URL_ORIGINAL, title=TITULO, source=SOURCE,
    wp_post_id=wp_id, fb_post_id=str(fb_id) if fb_id else None)

print(f"\nOK: WP={wp_id} | FB={'si' if fb_id else 'no'} | IG={'si' if ig_ok else 'no'}")
print(f"URL: {wp_url}")
print()
print("NOTA: Para agregar la imagen limpia, guardá la foto en tu escritorio")
print("o en Descargas con el nombre 'loteria-emoji.jpg' y volvé a correr el script.")
