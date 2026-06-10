"""Noticias generales de El Liberal — 03/06/2026 — redactadas por Claude"""
import json, requests, base64, time
from dotenv import dotenv_values
import database

env = dotenv_values(".env")
WP    = env["WP_URL"].rstrip("/")
TOKEN = env["META_ACCESS_TOKEN"]
PAGE  = env["FB_PAGE_ID"]
SOURCE = "El Liberal"

def wp_auth():
    t = base64.b64encode(f"{env['WP_USERNAME']}:{env['WP_APP_PASSWORD']}".encode()).decode()
    return {"Authorization": f"Basic {t}"}

def upload_og_image(url, filename):
    """Descarga la og:image de la nota y la sube a WP."""
    try:
        from bs4 import BeautifulSoup
        r = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        soup = BeautifulSoup(r.text, "lxml")
        og = soup.find("meta", property="og:image")
        if not og or not og.get("content"):
            return None, None
        img_url = og["content"]
        ri = requests.get(img_url, timeout=15); ri.raise_for_status()
        h = {**wp_auth(), "Content-Disposition": f'attachment; filename="{filename}"', "Content-Type": "image/jpeg"}
        r2 = requests.post(f"{WP}/wp-json/wp/v2/media", headers=h, data=ri.content, timeout=30)
        if r2.ok:
            d = r2.json(); return d.get("id"), d.get("source_url","")
    except Exception as e:
        print(f"  img error: {e}")
    return None, None

def post_wp(titulo, cuerpo, original_url, fecha, media_id=None):
    attr = f'<p><em>Fuente: <a href="{original_url}" target="_blank">{SOURCE}</a></em></p>'
    p = {"title": titulo, "content": cuerpo + attr, "status": "publish", "date": fecha}
    if media_id: p["featured_media"] = media_id
    r = requests.post(f"{WP}/wp-json/wp/v2/posts", json=p, headers=wp_auth(), timeout=30)
    r.raise_for_status()
    d = r.json(); return str(d["id"]), d.get("link","")

def post_fb(titulo, wp_url, image_url=None):
    # Link post estándar — aparece en feed móvil (NOT attached_media que va a Fotos)
    msg = f"📰 {titulo}\n\nLeé la nota completa 👇"
    r = requests.post(f"https://graph.facebook.com/v19.0/{PAGE}/feed",
        data={"message": msg, "link": wp_url, "access_token": TOKEN}, timeout=30)
    return r.json().get("id") if r.ok else None

def _post_fb_OLD_UNUSED(titulo, wp_url, image_url=None):
    msg = f"📰 {titulo}\n\nLeé la nota completa 👇\n{wp_url}"
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

FECHA_HOY = "2026-06-03"

ARTICULOS = [
  {
    "url": "https://www.elliberal.com.ar/nota/81801/2026/06/a-11-anos-del-ni-una-menos-santiago-del-estero-marcha-bajo-el-grito-de-paren-de-matarnos",
    "fecha": f"{FECHA_HOY}T18:00:00",
    "titulo": "A 11 años del primer Ni Una Menos, Santiago marchó con el grito de '¡Paren de matarnos!'",
    "cuerpo": """<p>Este martes, en el marco de los 11 años del movimiento Ni Una Menos, cientos de personas se movilizaron en Santiago del Estero bajo la consigna "¡Paren de matarnos!", convocadas por el Movimiento de Mujeres y Disidencias LGBTTTIQ+. La concentración central tuvo lugar en la intersección de Alvear y Belgrano, con inicio a las 18 horas.</p>
<p>La marcha volvió a poner en el centro del debate una estadística alarmante: en Argentina se registra un femicidio cada 44 horas. La movilización estuvo impulsada además por la conmoción que generó el caso de Agostina Vega, la adolescente de 14 años de Córdoba que desapareció el 23 de mayo y cuyo cuerpo fue hallado días después.</p>
<p>"Las consignas y las campañas que nacieron en las plazas hoy se repiten como miles de llamados de Justicia en cada rincón de la sociedad", expresaron desde la organización. El movimiento reclamó respuestas institucionales concretas, presupuesto genuino para la prevención de la violencia de género y una justicia con perspectiva de género que llegue a tiempo.</p>
<p>A once años de aquella primera convocatoria histórica, la marcha volvió a unir calles, hogares, escuelas y lugares de trabajo en torno a una misma exigencia que lejos de perder vigencia, gana urgencia con cada caso que sacude al país.</p>""",
  },
  {
    "url": "https://www.elliberal.com.ar/nota/81758/2026/06/convocan-a-familias-santiaguenas-para-adoptar-a-2-hermanitos",
    "fecha": f"{FECHA_HOY}T10:00:00",
    "titulo": "Mateo y Camila buscan una familia: convocan en Santiago para adoptar a dos hermanitos",
    "cuerpo": """<p>La Subsecretaría de Niñez, Adolescencia y Familia (Subnaf) de Santiago del Estero, junto al Poder Judicial, lanzó una convocatoria pública provincial para encontrar una familia adoptante para Mateo y Camila, dos hermanos que actualmente viven en el Hogar Eva Perón.</p>
<p>Mateo tiene 10 años: es inteligente, presenta discapacidad motriz y tiene una gran capacidad para aprender y superarse. Camila tiene 8 años: es alegre, le encanta bailar y es muy cariñosa. Ambos están escolarizados y participan activamente de actividades recreativas. El pedido central de las autoridades es que no sean separados.</p>
<p>"Buscamos una familia que pueda cuidar y acompañar responsablemente a Mateo y Camila", enfatizó Miriam Nallar, titular de la Subnaf. Pueden presentarse matrimonios, parejas convivientes o personas solteras mayores de 25 años. Las inscripciones se realizan a través de los formularios disponibles en los canales oficiales de la Subnaf y del Registro Único de Adoptantes.</p>
<p>Para quienes sientan el llamado de darles un hogar a estos dos chicos, el tiempo es clave. Mateo y Camila esperan una familia que los reciba juntos y los acompañe en su crecimiento.</p>""",
  },
  {
    "url": "https://www.elliberal.com.ar/nota/81765/2026/06/un-menor-santiagueno-intento-vender-un-arma-de-fuego-calibre-38-en-whatsapp",
    "fecha": f"{FECHA_HOY}T11:00:00",
    "titulo": "Intentó vender un revólver calibre 38 por WhatsApp: el implicado es un menor de 14 años",
    "cuerpo": """<p>Una fotografía de un revólver calibre 38 circulando en el estado de WhatsApp y en redes sociales desencadenó una investigación policial y judicial en el departamento Banda. El autor de la publicación resultó ser un adolescente de 14 años residente en Los Ardiles.</p>
<p>El hallazgo se produjo cerca del mediodía, cuando personal policial tomó conocimiento de la imagen que mostraba un arma de fuego de color negro. Efectivos de la Subcomisaría de Los Quirogas identificaron que la publicación provenía de una cuenta vinculada al menor y, por orden del fiscal de turno Dr. José Piña, se trasladaron a su domicilio.</p>
<p>Durante la intervención, en presencia de su padre, el adolescente explicó que la imagen le había sido enviada esa mañana a través de WhatsApp por un conocido apodado "Mochi" Bustos, quien le pidió que la publicara para conseguir un comprador. El menor aseguró no haber tenido el arma en su poder y que el presunto dueño se encontraría en Buenos Aires.</p>
<p>La investigación quedó abierta para determinar si existe un delito vinculado a la comercialización ilegal de armas de fuego y esclarecer el paradero del revólver.</p>""",
  },
  {
    "url": "https://www.elliberal.com.ar/nota/81780/2026/06/gustavo-wallberg--no-puede-quedarse-solo-enel-ajuste-el-plan-de-gobierno-nacional-no-puede-terminar-ahi",
    "fecha": f"{FECHA_HOY}T12:00:00",
    "titulo": "Economista santiagueño: 'El plan de Milei no puede quedarse solo en el ajuste'",
    "cuerpo": """<p>Gustavo Wallberg, titular del Instituto de Investigaciones Económicas de la UNT y reconocido economista con fuerte presencia en Santiago del Estero, reconoció los avances macroeconómicos del gobierno de Javier Milei pero marcó con claridad sus límites: "El plan de gobierno no puede terminar solo en el ajuste".</p>
<p>El especialista sostuvo que si bien la paralización inicial de la obra pública para alcanzar el superávit fiscal fue comprensible como primera medida, esta postura no puede convertirse en política permanente. Señaló además la ausencia de un programa de desarrollo regional como uno de los principales déficits de la gestión nacional, proponiendo que el gobierno impulse proyectos de infraestructura estratégica en las zonas con mayor rezago.</p>
<p>Wallberg advirtió que algunas decisiones controversiales del Ejecutivo erosionan innecesariamente el apoyo social a las reformas económicas, "debilitando la transición". Sus proyecciones para 2026 contemplan crecimiento moderado con inflación decreciente, aunque anticipó que la recuperación será desigual tanto por sectores como por regiones del país.</p>
<p>El economista disertará este viernes en las Segundas Jornadas de Economía que se realizarán en la Universidad Nacional de Santiago del Estero (UNSE).</p>""",
  },
  {
    "url": "https://www.elliberal.com.ar/nota/81788/2026/06/manuel-belgrano-su-nacimiento--3-de-junio-de-1770-",
    "fecha": f"{FECHA_HOY}T09:00:00",
    "titulo": "Hoy se cumplen 256 años del nacimiento de Manuel Belgrano, el creador de la Bandera",
    "cuerpo": """<p>Cada 3 de junio, la Argentina recuerda el nacimiento de Manuel Belgrano, uno de los próceres más completos de la historia nacional. Nacido en Buenos Aires en 1770, fue abogado, periodista, militar y político: el hombre que creó la Bandera Nacional y que donó el premio que recibió por sus victorias militares para construir cuatro escuelas en el norte del país.</p>
<p>Su historia tiene un vínculo especial con Santiago del Estero: su madre, María Josefa González Casero, tenía ancestros del pueblo de El Yugo, en las cercanías de Loreto, en esta provincia. Belgrano estudió derecho en las universidades de Salamanca y Valladolid, España, donde se graduó con distinción y obtuvo incluso permiso papal para leer obras de pensadores "prohibidos" como Montesquieu, Rousseau y Adam Smith, quienes moldearon su visión del mundo.</p>
<p>A su regreso al Río de la Plata en 1794, ocupó el cargo de Secretario del Real Consulado y comenzó a escribir las Memorias del Consulado, sembrando ideas de progreso económico y social. Fue también uno de los impulsores de la Revolución de Mayo, vocal de la Primera Junta y el conductor militar que con su victoria en la Batalla de Tucumán salvó la independencia de las Provincias Unidas.</p>
<p>A 256 años de su nacimiento, su figura sigue siendo símbolo de integridad, entrega y amor por la educación y la patria.</p>""",
  },
]

database.init_db()
publicados = 0
for art in ARTICULOS:
    if database.is_published(art["url"]):
        print(f"  Ya publicado: {art['titulo'][:50]}"); continue
    print(f"Publicando: {art['titulo'][:60]}")
    media_id, media_url = upload_og_image(art["url"], f"el-{art['url'].split('/')[-1][:20]}.jpg")
    try:
        wp_id, wp_url = post_wp(art["titulo"], art["cuerpo"], art["url"], art["fecha"], media_id)
        print(f"  WP={wp_id} | {art['fecha'][:10]}")
    except Exception as e:
        print(f"  WP error: {e}"); continue
    fb_id = post_fb(art["titulo"], wp_url, media_url)
    print(f"  FB={'OK' if fb_id else 'error'}")
    database.mark_published(url=art["url"], title=art["titulo"], source=SOURCE,
        wp_post_id=wp_id, fb_post_id=str(fb_id) if fb_id else None)
    publicados += 1
    time.sleep(4)

print(f"\nEl Liberal listo: {publicados} artículos publicados.")
