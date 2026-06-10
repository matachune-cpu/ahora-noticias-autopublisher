"""
Publica 3 noticias en orden intercalado:
1. La Banda (municipal)
2. Nacional (Senado / Milei)
3. Santiago Ciudad (municipal)
"""
import json, requests, base64, time, tempfile, os
from datetime import datetime
from dotenv import dotenv_values
import database, config
from flyer_generator import generate_flyer
from publishers import wordpress

env = dotenv_values(".env")
TOKEN = env["META_ACCESS_TOKEN"]
PAGE  = env["FB_PAGE_ID"]

def wp_auth():
    t = base64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {t}"}

def upload_img(url, filename):
    try:
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        r.raise_for_status()
        h = {**wp_auth(), "Content-Disposition": f'attachment; filename="{filename}"', "Content-Type": "image/jpeg"}
        r2 = requests.post(f"{env['WP_URL'].rstrip('/')}/wp-json/wp/v2/media", headers=h, data=r.content, timeout=30)
        if r2.ok: d = r2.json(); return d.get("id"), d.get("source_url","")
    except Exception as e: print(f"  img error: {e}")
    return None, None

def post_wp(titulo, cuerpo, original_url, source, media_id=None):
    attr = f'<p><em>Fuente: <a href="{original_url}" target="_blank">{source}</a></em></p>'
    p = {"title": titulo, "content": cuerpo + attr, "status": "publish"}
    if media_id: p["featured_media"] = media_id
    r = requests.post(f"{env['WP_URL'].rstrip('/')}/wp-json/wp/v2/posts",
        json=p, headers=wp_auth(), timeout=30)
    r.raise_for_status()
    d = r.json(); return str(d["id"]), d.get("link","")

def post_fb(titulo, wp_url, image_url=None, mensaje_extra=""):
    # Link post estándar — aparece en feed móvil (NOT attached_media que va a Fotos)
    msg = f"📰 {titulo}\n\n{mensaje_extra}\nLeé la nota completa 👇".strip()
    r = requests.post(f"https://graph.facebook.com/v19.0/{PAGE}/feed",
        data={"message": msg, "link": wp_url, "access_token": TOKEN}, timeout=30)
    return r.json().get("id") if r.ok else None

def _post_fb_OLD_UNUSED(titulo, wp_url, image_url=None, mensaje_extra=""):
    msg = f"📰 {titulo}\n\n{mensaje_extra}\nLeé la nota completa 👇\n{wp_url}".strip()
    if image_url:
        r1 = requests.post(f"https://graph.facebook.com/v19.0/{PAGE}/photos",
            data={"url": image_url, "published": "false", "access_token": TOKEN}, timeout=30)
        if r1.ok:
            photo_id = r1.json().get("id")
            r2 = requests.post(f"https://graph.facebook.com/v19.0/{PAGE}/feed",
                data={"message": msg, "attached_media[0]": json.dumps({"media_fbid": photo_id}),
                      "access_token": TOKEN}, timeout=30)
            if r2.ok: return r2.json().get("id")
    r = requests.post(f"https://graph.facebook.com/v19.0/{PAGE}/feed",
        data={"message": msg, "link": wp_url, "access_token": TOKEN}, timeout=30)
    return r.json().get("id") if r.ok else None

def encolar_ig(url, titulo, caption, img_url, source, score):
    flyer_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name
        generate_flyer(title=titulo, source_name=source, article_image_url=img_url,
            template_path=config.FLYER_TEMPLATE_PATH, output_path=flyer_path, categoria="")
        _, flyer_url = wordpress.upload_image(image_path=flyer_path,
            filename=f"flyer-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg")
        added = database.ig_queue_add(url=url, title=titulo, ig_caption=caption,
            flyer_public_url=flyer_url, relevance_score=score, source=source)
        return added
    except Exception as e:
        print(f"  IG error: {e}"); return False
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try: os.unlink(flyer_path)
            except: pass

ARTICULOS = [
    # ── 1. LA BANDA ──────────────────────────────────────────────────────────
    {
        "url": "https://labanda.gob.ar/noticias/6a1d90e0b7790b5b6c440798",
        "source": "Municipalidad La Banda",
        "img_url": "https://res.cloudinary.com/dteflhkxx/image/upload/v1780322527/prensa/w2l8un1jdrxeocgrorkr.webp",
        "ig_score": 6,
        "titulo": "La Banda tiene finalistas: el certamen de canto 'Dame Pista' eligió a sus mejores voces",
        "cuerpo": """<p>El certamen de canto "Dame Pista", organizado por la Dirección de Deportes y Recreación de la Municipalidad de La Banda, completó su tercera jornada de selección en el Cine Teatro Municipal Renzi y ya tiene definidos sus finalistas en ambas categorías.</p>
<p>El jurado evaluador, integrado por Beatriz Torres, Luciana Gutiérrez, Guillermo Amín y Gabriel Banegas, escuchó a los participantes y seleccionó a seis finalistas que representan distintos barrios de la ciudad.</p>
<p>En la categoría Juvenil clasificaron Dianela Fares (17 años, barrio Misky Mayu), Ana Brenda Nurit Sotelo (22 años, barrio Palermo) y Victoria Valentina Peralta Noriega (15 años, barrio El Rincón). En la categoría Adultos avanzaron Victoria Estefanía Ábalos (28 años, barrio San Fernando), Eduardo Omar Achaval (52 años, barrio Villa Rosita) y Carlos Alberto Giménez Jiménez (66 años, barrio Juan Felipe Ibarra).</p>
<p>Las semifinales están programadas para el 3 de junio a las 20:00 en el mismo escenario, y la gran final se realizará el 10 de junio, también en el Cine Teatro Renzi. Una iniciativa que pone en valor el talento musical de los vecinos bandeños.</p>""",
        "ig_caption": "🎤 ¡La Banda tiene finalistas! El certamen 'Dame Pista' ya eligió a sus mejores voces en el Cine Teatro Renzi. La final es el 10 de junio. ¡A apoyar el talento local! 🌟 #DamePista #LaBanda #SantiagoDelEstero #AhoraNoticias",
        "fb_extra": "🎤 El talento musical bandeño brilla en el certamen 'Dame Pista'. Ya están los finalistas de las categorías Juvenil y Adultos. La final es el 10 de junio en el Cine Teatro Renzi.",
    },
    # ── 2. NACIONAL ──────────────────────────────────────────────────────────
    {
        "url": "https://www.infobae.com/politica/2026/06/05/la-sesion-en-el-senado-desnudo-el-desorden-del-gobierno-y-la-interna-sumo-un-nuevo-capitulo/",
        "source": "Infobae",
        "img_url": None,
        "ig_score": 8,
        "titulo": "La interna de Milei al desnudo: el Senado aprobó a la jueza Michelli y quedaron expuestas las grietas del oficialismo",
        "cuerpo": """<p>La sesión del Senado del 5 de junio dejó al descubierto las tensiones internas del gobierno de Javier Milei. Con la aprobación del pliego de la jueza María Verónica Michelli —pese a los intentos del Ejecutivo de bloquearla— y la ratificación de otras 73 designaciones judiciales, la jornada parlamentaria terminó siendo un escenario incómodo para La Libertad Avanza.</p>
<p>El episodio más llamativo fue la abstención de Patricia Bullrich, jefa del bloque oficialista, al momento de votar contra Michelli, desoyendo las órdenes del Ejecutivo. Una fuente gubernamental lo resumió sin rodeos: "Es una disputa interna de poder constante".</p>
<p>El equipo del asesor Santiago Caputo apuntó contra los legisladores Eduardo y Martín Menem por la falta de coordinación parlamentaria. Por su parte, la vicepresidenta Victoria Villarruel expresó públicamente su apoyo a Michelli, complicando aún más el panorama interno.</p>
<p>Desde el Gobierno intentaron encuadrar el resultado como un éxito global —por la renovación judicial conseguida— y minimizaron el caso Michelli como un tema menor. Sin embargo, fuentes internas reconocieron frustración ante la independencia demostrada por Bullrich y las peleas sin resolver dentro del movimiento libertario. El Ejecutivo, además, dejó trascender que podría no firmar el decreto de nombramiento de la jueza.</p>""",
        "ig_caption": "🏛️ La interna de Milei al descubierto. El Senado aprobó a la jueza Michelli pese al intento del Ejecutivo de bloquearla. Bullrich se abstuvo. Villarruel apoyó. Las grietas del oficialismo quedaron expuestas en plena sesión. #Milei #Senado #LaBanda #AhoraNoticias",
        "fb_extra": "🏛️ Sesión caliente en el Senado: la aprobación de la jueza Michelli expuso las tensiones internas del gobierno de Milei. Bullrich desoyó al Ejecutivo y Villarruel tomó partido.",
    },
    # ── 3. SANTIAGO CIUDAD ────────────────────────────────────────────────────
    {
        "url": "https://www.santiagociudad.gov.ar/noticias/3073-la-intendente-superviso-areas-operativas-en-el-barrio-borges",
        "source": "Santiago Ciudad",
        "img_url": "https://www.santiagociudad.gov.ar/images/noticias/3073.jpg",
        "ig_score": 5,
        "titulo": "La intendente Fuentes supervisó operativos integrales en el barrio Borges: limpieza, iluminación LED y cámaras de seguridad",
        "cuerpo": """<p>La intendente Ing. Norma Fuentes recorrió este jueves el barrio Borges de la ciudad capital para supervisar los operativos de mejora urbana que lleva adelante el municipio, con foco en la recuperación del espacio público y el cuidado ambiental.</p>
<p>Los trabajos incluyeron limpieza y erradicación de basurales clandestinos, tareas de bacheo y reparación de calles con hormigón, podas de árboles y desmalezamiento, instalación de nuevas columnas de iluminación LED y colocación de cámaras de seguridad en puntos estratégicos del barrio.</p>
<p>En la intersección de las calles 11 y 14, los equipos municipales despejaron un terreno con importante acumulación de escombros y residuos, habilitando además el acceso hacia la Avenida Diaguitas. La instalación de luminarias en ese sector busca disuadir el arrojo ilegal de basura, un problema recurrente que los vecinos habían denunciado reiteradamente.</p>
<p>"Estas acciones apuntan a mantener una ciudad limpia y ordenada, recuperando los espacios públicos para el disfrute de toda la comunidad", destacó la jefa comunal durante el recorrido. El municipio también instó a los vecinos a respetar los horarios del servicio de recolección y a utilizar los sitios habilitados para el descarte de residuos.</p>""",
        "ig_caption": "🏘️ Barrio Borges de pie. La intendente Fuentes supervisó operativos de limpieza, iluminación LED y cámaras de seguridad en el barrio. El municipio avanza en la recuperación del espacio público. 💪 #SantiagoDelEstero #BarrioBorges #AhoraNoticias",
        "fb_extra": "🏘️ El municipio de Santiago Capital intervino hoy en el barrio Borges con limpieza de basurales, bacheo, iluminación LED y nuevas cámaras de seguridad.",
    },
]

database.init_db()
publicados = 0

for art in ARTICULOS:
    if database.is_published(art["url"]):
        print(f"  Ya publicado: {art['titulo'][:55]}")
        continue

    print(f"\n[{art['source']}] {art['titulo'][:65]}")

    # Imagen
    media_id, media_url = None, None
    if art["img_url"]:
        media_id, media_url = upload_img(art["img_url"], f"img-{datetime.now().strftime('%H%M%S')}.jpg")

    # WordPress
    try:
        wp_id, wp_url = post_wp(art["titulo"], art["cuerpo"], art["url"], art["source"], media_id)
        print(f"  WP={wp_id} ✓")
    except Exception as e:
        print(f"  WP error: {e}"); continue

    # Facebook
    fb_image = media_url or art["img_url"]
    fb_id = post_fb(art["titulo"], wp_url, fb_image, art.get("fb_extra",""))
    print(f"  FB={'OK' if fb_id else 'error'}")

    # Instagram (encolar)
    ig = encolar_ig(art["url"], art["titulo"], art["ig_caption"],
                    art["img_url"], art["source"], art["ig_score"])
    print(f"  IG={'encolado' if ig else 'ya en cola'} (score={art['ig_score']})")

    database.mark_published(url=art["url"], title=art["titulo"], source=art["source"],
        wp_post_id=wp_id, fb_post_id=str(fb_id) if fb_id else None)

    publicados += 1
    time.sleep(5)

print(f"\n{'='*50}")
print(f"Publicados: {publicados}/3 | Orden: La Banda → Nacional → Santiago Ciudad")
