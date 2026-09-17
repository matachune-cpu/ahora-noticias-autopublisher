"""
Batch de 5 notas urgentes del 17 de septiembre de 2026.
Publica en WP + IG + FB en secuencia.
"""
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
logger = logging.getLogger("batch_17sep")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}
_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")

# ══════════════════════════════════════════════════════════════════════════════
# NOTA 1 — Ley de Defensa de la Soberanía por Malvinas
# ══════════════════════════════════════════════════════════════════════════════
NOTA1 = {
    "url_canonica": "https://www.canal26.com/politica/2026/09/17/regimen-de-derribo-sanciones-economicas-y-penas-de-hasta-20-anos-uno-por-uno-los-puntos-clave-de-la-ley-de-defensa-de-la-soberania-por-malvinas/",
    "fuente": "Canal 26",
    "titulo_wp": "Milei envió al Congreso la ley de soberanía por Malvinas: derribo de aviones, hundimiento de buques y hasta 20 años de prisión",
    "titulo_flyer": "URGENTE: Milei manda al Congreso ley de soberanía — derribo de aviones y 20 años de cárcel",
    "categoria": "Política",
    "sticky": True,
    "categorias_wp": ["Política", "Malvinas"],
    "fuentes_imagen": [
        "https://www.losandes.com.ar/politica/malvinas-las-claves-del-proyecto-que-milei-envio-al-congreso-endurecer-sanciones-explotar-los-recursos-n6006605",
        "https://www.mdzol.com/politica/el-gobierno-presento-el-proyecto-malvinas-endurece-sanciones-ley-derribo-y-penas-20-anos-n1608756",
        "https://www.analisisdigital.com.ar/nacionales/2026/09/17/milei-envio-al-congreso-la-ley-de-defensa-de-la-soberania-nacional-por-malvinas",
    ],
    "cuerpo_html": """
<p><strong>El presidente Javier Milei envió este miércoles al Congreso de la Nación el proyecto
de Ley de Defensa de la Soberanía Nacional por Malvinas</strong>, una iniciativa que endurece
drásticamente las sanciones contra quienes exploten recursos en las Islas Malvinas sin autorización
argentina, habilita el derribo de aeronaves y el hundimiento de embarcaciones consideradas una
amenaza, y crea un Consejo de Seguridad Nacional.</p>

<h2>Las claves del proyecto</h2>

<p>El proyecto reemplaza la Ley 26.659 vigente desde 2011, que se concentraba exclusivamente en
exploración y explotación de hidrocarburos. La nueva norma amplía el alcance a cualquier uso no
autorizado de recursos naturales —renovables o no renovables— en el área soberana en disputa.</p>

<p>Entre los puntos centrales se destacan:</p>
<ul>
<li><strong>Régimen de derribo:</strong> habilita a las Fuerzas Armadas a derribar aeronaves y
hundir embarcaciones que operen en el área sin permiso argentino y no respondan a las intimaciones
oficiales.</li>
<li><strong>Penas de hasta 20 años de prisión</strong> para quienes exploten ilegalmente recursos
naturales en las islas o la plataforma continental argentina.</li>
<li><strong>Multas millonarias:</strong> sanciones económicas de hasta diez veces el valor de los
recursos extraídos ilegalmente.</li>
<li><strong>Inhabilitación perpetua</strong> para empresas que operen sin autorización argentina.</li>
<li><strong>Consejo de Seguridad Nacional:</strong> nuevo organismo que articula herramientas
diplomáticas, económicas, de defensa, legales e inteligencia para proteger la soberanía.</li>
</ul>

<h2>El contexto: tensión con el Reino Unido</h2>

<p>La iniciativa llega en un momento de alta tensión diplomática. Días atrás, el Ministro de
Defensa británico, John Healey, advirtió sobre el "alerta máxima" de las Fuerzas Armadas del
Reino Unido ante las medidas argentinas. La Asamblea Legislativa de las islas, por su parte,
calificó los reclamos de Milei como "infructuosas tácticas de bullying" con motivación electoral.</p>

<p>El proyecto deberá recorrer el Parlamento en un contexto político complejo, con el oficialismo
en minoría en ambas cámaras, aunque el tema Malvinas genera consenso transversal en la mayoría
de los bloques.</p>

<p><em>Fuente: Canal 26 / Los Andes / Análisis Digital</em></p>
""",
}

# ══════════════════════════════════════════════════════════════════════════════
# NOTA 2 — Estudiantes a semifinales Copa Libertadores
# ══════════════════════════════════════════════════════════════════════════════
NOTA2 = {
    "url_canonica": "https://www.lanacion.com.ar/deportes/futbol/corinthians-vs-estudiantes-de-la-plata-en-vivo-nid16092026/",
    "fuente": "La Nación",
    "titulo_wp": "Histórico: Estudiantes venció 1-0 a Corinthians en Brasil y se metió en las semifinales de la Copa Libertadores 2026 tras 17 años",
    "titulo_flyer": "¡HISTÓRICO! Estudiantes a las semis de la Copa Libertadores: venció 1-0 a Corinthians en Brasil",
    "categoria": "Deportes",
    "sticky": False,
    "categorias_wp": ["Deportes"],
    "fuentes_imagen": [
        "https://www.eluniverso.com/deportes/futbol/semifinales-de-la-copa-libertadores-2026-clasificados-y-como-quedarian-las-llaves-nota/",
        "https://www.catamarcactual.com.ar/deportes/2026/9/16/estudiantes-la-semi-de-la-libertadores-315487.html",
        "https://www.diariopanorama.com/noticia/566707/copa-libertadores-2026-cuando-juega-estudiantes-semifinales-posibles-rivales-donde-define",
    ],
    "cuerpo_html": """
<p><strong>Estudiantes de La Plata escribió una página histórica en la Copa Libertadores 2026.</strong>
El Pincha venció 1-0 a Corinthians en la Neo Química Arena de San Pablo con un gol de Alexis Castro
en el tramo final del partido y se clasificó a las semifinales del torneo más importante del
continente, una instancia que no alcanzaba desde 2009, cuando levantó el trofeo.</p>

<h2>El partido</h2>

<p>La serie había terminado 1-1 en La Plata en el partido de ida, por lo que Estudiantes necesitaba
ganar o empatar para avanzar por diferencia de goles de visitante. El equipo dirigido por Eduardo
Domínguez apostó a la solidez defensiva y al contragolpe, y el plan funcionó a la perfección.</p>

<p>El gol de Castro llegó en el cierre del partido y desató el delirio entre los cientos de
hinchas de Estudiantes que viajaron a Brasil para acompañar al equipo. El Pincha no solo ganó:
lo hizo en condición de visitante ante uno de los grandes de Brasil.</p>

<h2>El cuadro de semifinales</h2>

<p>Estudiantes esperará al ganador del cruce entre <strong>Flamengo e Independiente del Valle</strong>,
que define este jueves desde las 21:30 en Brasil. El Mengão ganó 2-0 en Ecuador en el partido de
ida y llega como amplio favorito.</p>

<p>La llave opuesta enfrenta a los clasificados del otro cuartel, en un cuadro que promete
semifinales de alto voltaje.</p>

<h2>Las fechas</h2>

<p>Los partidos de ida de las semifinales se disputarán entre el <strong>13 y 14 de octubre</strong>,
y las revanchas entre el <strong>20 y 21 de octubre</strong>. La final será a partido único el
<strong>28 de noviembre en el Estadio Centenario de Montevideo</strong>.</p>

<p>Estudiantes tiene la ventaja de disputar la revancha como visitante —lo que en la práctica
significa que con un empate pasa si ganó la ida— y tendrá que salir a ganar el primero en La Plata.</p>

<p><em>Fuente: La Nación / 365Scores / Diario Panorama</em></p>
""",
}

# ══════════════════════════════════════════════════════════════════════════════
# NOTA 3 — INDEC: PBI y desempleo 2T 2026
# ══════════════════════════════════════════════════════════════════════════════
NOTA3 = {
    "url_canonica": "https://www.elliberal.com.ar/nota/91846/2026/09/indec-publica-hoy-los-datos-de-pib-y-empleo--que-se-espera-para-la-economia-argentina",
    "fuente": "El Liberal",
    "titulo_wp": "El INDEC publica hoy los datos del PBI y el desempleo del segundo trimestre: qué se espera y cómo le fue a la economía argentina",
    "titulo_flyer": "INDEC hoy: PBI y desempleo del 2do trimestre — los datos clave de la economía argentina",
    "categoria": "Economía",
    "sticky": False,
    "categorias_wp": ["Economía", "Nacionales"],
    "fuentes_imagen": [
        "https://comercioyjusticia.info/economia/indec-crecimiento-de-la-economia-y-tasa-de-desempleo-en-argentina/",
        "https://www.launion.digital/economia/hoy-conocen-datos-indec-sobre-crecimiento-economia-tasa-desempleo-n242971",
        "https://panoramadirecto.com/atencion-indec-revela-hoy-el-dato-mas-esperado-sobre-la-economia-y-el-empleo/",
    ],
    "cuerpo_html": """
<p><strong>Este jueves, el Instituto Nacional de Estadística y Censos (INDEC) publicará dos de
los indicadores más esperados del año: el crecimiento del Producto Bruto Interno (PBI) del segundo
trimestre de 2026 y la evolución del desempleo en el mismo período.</strong> Los datos llegarán
en un contexto económico particular, marcado por la recuperación gradual tras el ajuste de 2024
y el debate sobre si el "peso fuerte" sostenido por el gobierno de Javier Milei puede afectar la
competitividad de la economía.</p>

<h2>Qué pasó en el primer trimestre</h2>

<p>El punto de partida es positivo: en el primer trimestre de 2026, el PBI creció <strong>0,7%
respecto al trimestre anterior</strong> y <strong>2,3% en comparación interanual</strong>. Doce
de los 16 sectores que componen el estimador mostraron mejora anual, con las exportaciones como
principal motor (crecieron 9,8% anual) y el consumo de los hogares también en terreno positivo
(+2,7% anual).</p>

<p>En materia laboral, el desempleo se ubicó en <strong>7,8%</strong> durante el primer trimestre,
con una tasa de actividad del 48,6% y empleo del 44,8%.</p>

<h2>Qué se espera para el segundo trimestre</h2>

<p>Los economistas proyectan un crecimiento moderado para el período abril-junio, aunque han
recortado sus estimaciones para el año completo al 2,1% (desde el 3,5% previsto meses atrás).
La política cambiaria —que mantiene el tipo de cambio en torno a los 1.500 pesos por dólar—
genera debate sobre si el peso apreciado puede afectar la competitividad de las exportaciones
y frenar la recuperación.</p>

<p>En cuanto al empleo, se espera que la tasa de desempleo se haya mantenido estable o con leve
mejora respecto al trimestre anterior, en línea con la recuperación de la actividad.</p>

<h2>El dato de la inflación</h2>

<p>Como contexto, la inflación mensual bajó al <strong>1,7% en agosto</strong>, muy por debajo
del 25,5% que registraba cuando Milei asumió la presidencia. El dato de hoy permitirá evaluar
si el enfriamiento de precios viene acompañado de crecimiento real o si implica un freno de la
actividad económica.</p>

<p><em>Fuente: El Liberal / Rosario Finanzas / Comercio y Justicia</em></p>
""",
}

# ══════════════════════════════════════════════════════════════════════════════
# NOTA 4 — Peso fuerte de Milei preocupa a analistas internacionales
# ══════════════════════════════════════════════════════════════════════════════
NOTA4 = {
    "url_canonica": "https://www.infobae.com/economia/2026/09/17/por-que-el-peso-fuerte-de-milei-puede-frenar-la-actividad-economica-en-argentina-segun-un-agencia-internacional/",
    "fuente": "Infobae",
    "titulo_wp": "El peso fuerte de Milei genera alerta internacional: analistas advierten que puede frenar la actividad económica argentina",
    "titulo_flyer": "Alerta internacional: el peso fuerte de Milei puede frenar la economía argentina",
    "categoria": "Economía",
    "sticky": False,
    "categorias_wp": ["Economía", "Nacionales"],
    "fuentes_imagen": [
        "https://eleconomista.com.ar/",
        "https://comercioyjusticia.info/economia/indec-crecimiento-de-la-economia-y-tasa-de-desempleo-en-argentina/",
        "https://panoramadirecto.com/atencion-indec-revela-hoy-el-dato-mas-esperado-sobre-la-economia-y-el-empleo/",
    ],
    "cuerpo_html": """
<p><strong>Una agencia internacional de análisis económico encendió señales de alerta sobre la
estrategia cambiaria del gobierno de Javier Milei.</strong> Según el informe, el "peso fuerte"
—la política de mantener el tipo de cambio en torno a los 1.500 pesos por dólar, muy por debajo
de lo que preveían los analistas— podría convertirse en un freno para la actividad económica
argentina en los próximos meses.</p>

<h2>El diagnóstico</h2>

<p>Los economistas que elaboraron el informe destacan que, si bien la apreciación del peso ha sido
clave para dominar la inflación (que bajó del 25,5% mensual en diciembre de 2023 al 1,7% en
agosto de 2026), el efecto secundario es una pérdida de competitividad de las exportaciones
argentinas frente a sus competidores regionales.</p>

<p>La proyección de crecimiento para todo 2026 fue recortada al <strong>2,1%</strong>, desde el
<strong>3,5%</strong> estimado meses atrás. El principal factor de revisión es el tipo de cambio
real, que presiona sobre los sectores exportadores no agrícolas y sobre la industria que compite
con importaciones.</p>

<h2>El dilema del gobierno</h2>

<p>El gobierno enfrenta un dilema clásico: una devaluación aliviaria la presión sobre el sector
externo pero reavivación las expectativas inflacionarias, poniendo en riesgo el logro central del
modelo. Milei y el ministro de Economía han reiterado que no habrá devaluación brusca y que la
competitividad deberá recuperarse por la vía de la baja de costos y la desregulación.</p>

<p>El mercado, por su parte, mantiene expectativas de una corrección gradual del tipo de cambio
hacia fin de año, aunque el Banco Central ha intervenido en los últimos meses para sostener la
paridad dentro de la banda establecida.</p>

<h2>La inflación, en mínimos históricos recientes</h2>

<p>El dato que el gobierno defiende como su principal logro es la caída de la inflación. En agosto,
el índice mensual se ubicó en 1,7%, el nivel más bajo desde el inicio de la gestión. Sin embargo,
los analistas advierten que el costo del ancla cambiaria podría hacerse visible en los próximos
trimestres en términos de menor crecimiento y empleo.</p>

<p><em>Fuente: Infobae / El Economista</em></p>
""",
}

# ══════════════════════════════════════════════════════════════════════════════
# NOTA 5 — Islas Malvinas llaman "bullying" a Milei
# ══════════════════════════════════════════════════════════════════════════════
NOTA5 = {
    "url_canonica": "https://unitel.bo/noticias/agencias/jueves-17-de-septiembre-de-2026-0200-gmt-HA23545570",
    "fuente": "Agencias internacionales",
    "titulo_wp": "La Asamblea Legislativa de Malvinas le respondió a Milei: llamó sus reclamos 'infructuosas tácticas de bullying' con motivos electorales",
    "titulo_flyer": "Malvinas le responde a Milei: 'Son infructuosas tácticas de bullying con motivos electorales'",
    "categoria": "Malvinas",
    "sticky": False,
    "categorias_wp": ["Política", "Malvinas"],
    "fuentes_imagen": [
        "https://www.losandes.com.ar/politica/malvinas-las-claves-del-proyecto-que-milei-envio-al-congreso-endurecer-sanciones-explotar-los-recursos-n6006605",
        "https://www.mdzol.com/politica/el-gobierno-presento-el-proyecto-malvinas-endurece-sanciones-ley-derribo-y-penas-20-anos-n1608756",
        "https://nuevospapeles.com/nota/puntos-principales-del-proyecto-de-ley-de-defensa-de-la-soberania-nacional/",
    ],
    "cuerpo_html": """
<p><strong>El presidente de la Asamblea Legislativa de las Islas Malvinas, Jack Ford, salió a
responderle al presidente Javier Milei y descartó de manera contundente los renovados reclamos
de soberanía del mandatario argentino.</strong> En declaraciones difundidas este jueves, Ford
calificó las acciones de Milei como "infructuosas tácticas de bullying" y aseguró que tienen
motivaciones puramente electorales de cara a los comicios legislativos de 2027.</p>

<h2>"No cambia nada"</h2>

<p>Ford fue categórico al evaluar el proyecto de ley enviado al Congreso argentino, que habilita
el derribo de aeronaves y el hundimiento de buques en el área en disputa, y establece penas de
hasta 20 años de prisión para quienes exploten recursos sin autorización de Buenos Aires.</p>

<p>"Nada de esto cambia la situación. Las Islas Malvinas son territorio británico de ultramar y
sus habitantes tienen el derecho de determinar su propio futuro", sostuvo el funcionario isleño.
"Este tipo de retórica agresiva no intimida a nadie; es política interna argentina, nada más."</p>

<h2>La posición del Reino Unido</h2>

<p>El Ministro de Defensa británico, John Healey, había advertido días atrás que las Fuerzas
Armadas del Reino Unido se encontraban en "alerta máxima" ante las medidas del gobierno
argentino. Londres reafirmó que no negociará la soberanía de las islas.</p>

<h2>La mirada argentina</h2>

<p>Desde Buenos Aires, el gobierno de Milei insiste en que la causa Malvinas es una cuestión
de Estado que trasciende las diferencias partidarias. La Cancillería rechazó las declaraciones
de Ford y reiteró que la Argentina reclama sus derechos soberanos por vías pacíficas y en el
marco del derecho internacional.</p>

<p>El proyecto de Ley de Defensa de la Soberanía Nacional deberá recorrer el Congreso, donde
el kirchnerismo y otros bloques también han manifestado apoyo a endurecer las sanciones, aunque
con matices respecto al régimen de derribo.</p>

<p><em>Fuente: Agencias internacionales / Los Andes</em></p>
""",
}

NOTAS = [NOTA1, NOTA2, NOTA3, NOTA4, NOTA5]


def _buscar_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return None
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                img = tag["content"]
                if img.startswith("http") and not any(s in img.lower() for s in _LOGO_SIGNALS):
                    return img
    except Exception:
        pass
    return None


def _buscar_imagen(fuentes: list) -> str | None:
    for url in fuentes:
        img = _buscar_og_image(url)
        if img:
            logger.info(f"  Imagen: {img[:80]}")
            return img
    return None


def _generar_captions_gemini(titulo: str, contexto: str, categoria: str, wp_link: str) -> dict:
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")
        client = genai.Client(api_key=key)
        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            f"Generá DOS textos para esta nota de {categoria}:\n\n"
            f"TITULAR: '{titulo}'\n\n"
            f"CONTEXTO: {contexto}\n\n"
            "TEXTO 1 — Caption Instagram (máx 140 palabras):\n"
            "- Tono: urgente, informativo, gancho inicial\n"
            f"- Cerrá con: #AhoraNoticias #{categoria.replace(' ', '')} #Argentina\n\n"
            "TEXTO 2 — Copy Facebook (máx 70 palabras):\n"
            "- Directo, sin hashtags\n"
            f"- Cerrá con: 'Leé la nota completa → {wp_link}'\n\n"
            "Respondé EXACTAMENTE:\n===INSTAGRAM===\n[caption]\n===FACEBOOK===\n[copy]\n"
        )
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        raw = response.text.strip()
        ig, fb = "", ""
        if "===INSTAGRAM===" in raw and "===FACEBOOK===" in raw:
            parts = raw.split("===FACEBOOK===")
            ig = parts[0].replace("===INSTAGRAM===", "").strip()
            fb = parts[1].strip()
        else:
            ig = raw[:500]
            fb = raw[:300]
        return {"instagram": ig, "facebook": fb}
    except Exception as e:
        logger.warning(f"Gemini no disponible: {e}")
        ig = f"🚨 {titulo}\n\n📰 Ahora Noticias | Santiago del Estero\n\n#AhoraNoticias #{categoria.replace(' ', '')} #Argentina"
        fb = f"{titulo}\n\nLeé la nota completa → {wp_link}"
        return {"instagram": ig, "facebook": fb}


def publicar_nota(nota: dict) -> bool:
    url_can = nota["url_canonica"]
    titulo = nota["titulo_wp"]

    if database.is_published(url_can):
        logger.warning(f"Ya publicada: {titulo[:60]}")
        return False

    logger.info(f"\n{'═'*60}")
    logger.info(f"Publicando: {titulo[:70]}")
    logger.info(f"{'═'*60}")

    img_url = _buscar_imagen(nota["fuentes_imagen"])
    if not img_url:
        logger.error("Sin imagen. Saltando nota.")
        return False

    # WordPress
    wp_img_id = None
    try:
        slug = titulo[:30].lower().replace(" ", "-").replace(":", "").replace(",", "")
        r = wordpress.upload_image(image_url=img_url, filename=f"{slug}-{datetime.now().strftime('%Y%m%d')}.jpg")
        if isinstance(r, tuple):
            wp_img_id, _ = r
    except Exception as e:
        logger.warning(f"Imagen WP: {e}")

    cat_ids = []
    for cat in nota.get("categorias_wp", [nota["categoria"]]):
        try:
            cid = wordpress.get_or_create_category(cat)
            if cid:
                cat_ids.append(cid)
        except Exception:
            pass

    try:
        wp_result = wordpress.create_post(
            title=titulo,
            body_html=nota["cuerpo_html"],
            original_url=url_can,
            source_name=nota["fuente"],
            featured_media_id=wp_img_id,
            sticky=nota.get("sticky", False),
            categories=cat_ids,
        )
    except Exception as e:
        logger.error(f"Error WP: {e}")
        return False

    if not wp_result:
        logger.error("WP no respondió.")
        return False

    if isinstance(wp_result, tuple):
        wp_id, wp_link = wp_result
    else:
        wp_id = wp_result.get("id") if isinstance(wp_result, dict) else None
        wp_link = wp_result.get("link", "https://ahoranoticias.com.ar") if isinstance(wp_result, dict) else "https://ahoranoticias.com.ar"

    logger.info(f"✓ WordPress: ID={wp_id} | {wp_link}")

    if wp_id and nota.get("sticky"):
        try:
            wordpress.rotate_sticky_posts(new_post_ids=[int(wp_id)], max_sticky=4)
        except Exception as e:
            logger.warning(f"Rotate sticky: {e}")

    database.mark_published(url_can, titulo, nota["fuente"], wp_post_id=str(wp_id) if wp_id else None)

    # Captions
    contexto_breve = nota["cuerpo_html"].replace("<p>", "").replace("</p>", " ").replace("<h2>", "").replace("</h2>", ". ").replace("<ul>", "").replace("</ul>", "").replace("<li>", "- ").replace("</li>", ". ").replace("<strong>", "").replace("</strong>", "")[:600]
    captions = _generar_captions_gemini(titulo, contexto_breve, nota["categoria"], wp_link)

    # Flyer
    flyer_path = None
    flyer_url = None
    try:
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            flyer_path = tmp.name
        generate_flyer(
            title=nota["titulo_flyer"],
            source_name="Ahora Noticias",
            article_image_url=img_url,
            template_path=config.FLYER_TEMPLATE_PATH,
            output_path=flyer_path,
            categoria=nota["categoria"],
        )
        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        slug_flyer = titulo[:20].lower().replace(" ", "-").replace(":", "")
        up = wordpress.upload_image(flyer_path, f"flyer-{slug_flyer}-{ts}.jpg")
        if isinstance(up, tuple):
            _, flyer_url = up
        logger.info(f"✓ Flyer: {(flyer_url or '')[:70]}")
    except Exception as e:
        logger.error(f"Error flyer: {e}")
    finally:
        if flyer_path and os.path.exists(flyer_path):
            try:
                os.unlink(flyer_path)
            except Exception:
                pass

    if not flyer_url:
        logger.error("Sin flyer URL. Saltando redes.")
        return True  # WP ok igual

    # Instagram
    ig_id = None
    try:
        ig_id = instagram.post_image(image_path=None, caption=captions["instagram"], public_image_url=flyer_url)
        logger.info(f"✓ Instagram: {'ID=' + str(ig_id) if ig_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Instagram: {e}")

    # Facebook
    fb_id = None
    try:
        fb_id = facebook.post_link(
            title=titulo,
            wp_post_url=wp_link,
            original_url=wp_link,
            image_url=flyer_url,
            caption=captions["facebook"],
        )
        logger.info(f"✓ Facebook: {'ID=' + str(fb_id) if fb_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Facebook: {e}")

    logger.info(f"  WP={wp_link} | IG={ig_id or 'x'} | FB={fb_id or 'x'}")
    return True


def main():
    database.init_db()
    exitosas = 0
    for i, nota in enumerate(NOTAS, 1):
        logger.info(f"\n>>> NOTA {i}/{len(NOTAS)}")
        ok = publicar_nota(nota)
        if ok:
            exitosas += 1
        if i < len(NOTAS):
            time.sleep(5)

    logger.info(f"\n{'━'*55}")
    logger.info(f"  BATCH COMPLETO: {exitosas}/{len(NOTAS)} publicadas")
    logger.info(f"{'━'*55}")


if __name__ == "__main__":
    main()
