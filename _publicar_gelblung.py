"""
Publica en WP + IG + FB la nota sobre la muerte de Chiche Gelblung.
"""
import logging
import os
import tempfile
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
logger = logging.getLogger("gelblung")

# ── CONSTANTES ────────────────────────────────────────────────────────────────

TITULO_WP = (
    "Murió Chiche Gelblung a los 82 años: el periodista que soñaba con vivir 200 años "
    "y le dio voz a lo que nadie se animaba a decir"
)

TITULO_FLYER = "Murió Chiche Gelblung a los 82 años: adiós a una leyenda del periodismo argentino"

CATEGORIA = "Espectáculos"

URL_CANONICA = "https://www.minutouno.com/sociedad/murio-samuel-chiche-gelblung-emblematico-periodista-y-fundador-minutounocom-n6283231"
FUENTE = "Minuto Uno"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

_LOGO_SIGNALS = ("logo", "default", "placeholder", "noimage", "favicon", "brand", "watermark")

CUERPO_HTML = """
<p>El periodismo argentino está de luto. Samuel "Chiche" Gelblung murió este miércoles
9 de septiembre de 2026, a los 82 años, mientras se encontraba internado en el Sanatorio
Mater Dei de Buenos Aires, donde ingresó días atrás por una complicación respiratoria que
se fue agravando hasta que su corazón no pudo más.</p>

<p>La noticia fue confirmada por Crónica TV y rápidamente se propagó por todos los medios
argentinos, desatando una ola de condolencias de colegas, famosos, políticos y seguidores
de un comunicador que durante más de seis décadas fue un referente ineludible —y polémico—
de la televisión, la radio y el periodismo gráfico en la Argentina.</p>

<h2>Una vida consagrada a los medios</h2>

<p>Nacido el 7 de febrero de 1944, Gelblung comenzó su carrera en 1966 en la revista
<em>Gente</em>, donde se desempeñó como fotógrafo y cronista. Desde temprano mostró
ese instinto para buscar la noticia donde nadie más miraba, una característica que lo
acompañaría durante toda su trayectoria.</p>

<p>Trabajó como corresponsal de guerra, condujo programas en Radio 10, Radio Mitre y
Radio Rivadavia —con ciclos como "Edición Chiche" y "Hola Chiche"— y se convirtió en
una de las figuras más reconocibles de la pantalla argentina.</p>

<h2>'Memoria': el programa que lo hizo inmortal</h2>

<p>Su mayor legado televisivo fue <em>Memoria</em>, emitido por Canal 9 desde los años 90
hasta 2002. El ciclo, que arrancó con Silvia Fernández Barrio y luego quedó bajo su
conducción exclusiva, combinaba investigación periodística, entrevistas de alto impacto,
misterio y relatos de casos que conmovían al país entero. El programa fue pionero de un
formato que otros canales intentaron imitar sin éxito.</p>

<p>También formó parte de ciclos como "Polémica en el bar", "Chiche en vivo" y "70.20.10",
siempre con su estilo inconfundible: directo, sin filtros, con un humor ácido y una
capacidad única para conseguir que sus entrevistados dijeran lo que nadie más lograba
arrancarles.</p>

<h2>El fundador de Minuto Uno</h2>

<p>En 2006, cuando el periodismo digital argentino daba sus primeros pasos, Gelblung fundó
Minuto Uno, un portal de noticias que se convirtió en uno de los sitios de información
más visitados del país. Su visión de los medios siempre estuvo por delante de su época.</p>

<h2>Su último año: la salud como desafío</h2>

<p>En mayo pasado, Chiche había atravesado un episodio delicado que lo llevó a terapia
intensiva en el Sanatorio De Los Arcos, donde también le colocaron un stent en una
pierna tras sufrir una trombosis en el tobillo. Se había recuperado, pero el sistema
respiratorio volvió a fallar en estas últimas semanas.</p>

<p>Hasta el final, el periodista que alguna vez dijo querer vivir 200 años y viajar a
la luna siguió siendo fiel a su leyenda: irreverente, apasionado y sin miedo a nada.</p>

<p>El periodismo argentino pierde hoy a uno de sus personajes más grandes. Chiche
Gelblung tenía 82 años.</p>

<p><em>Fuente: Minuto Uno / Infobae / La Nación</em></p>
"""

# ── FUENTES DE IMAGEN ─────────────────────────────────────────────────────────

FUENTES_IMAGEN = [
    "https://www.infobae.com/teleshow/2026/09/09/murio-chiche-gelblung-el-periodista-que-sonaba-con-viajar-a-la-luna-y-vivir-200-anos/",
    "https://www.lanacion.com.ar/espectaculos/personajes/murio-chiche-gelblung-a-los-82-anos-se-encontraba-en-terapia-intensiva-nid09092026/",
    "https://www.perfil.com/noticias/protagonistas/murio-chiche-gelblung-a-los-82-anos.phtml",
    "https://www.canal26.com/espectaculos/2026/09/09/de-que-murio-chiche-gelblung-que-problema-de-salud-tenia-el-historico-periodista-argentino/",
    "https://misionesonline.net/2026/09/09/murio-chiche-gelblung/",
]


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
                    logger.info(f"  Imagen: {img[:80]}")
                    return img
    except Exception as e:
        logger.debug(f"og:image {url}: {e}")
    return None


def _buscar_imagen() -> str | None:
    for url in FUENTES_IMAGEN:
        img = _buscar_og_image(url)
        if img:
            return img
    return None


def _generar_captions_gemini(wp_link: str) -> dict:
    try:
        from google import genai
        key = os.getenv("GEMINI_API_KEY")
        if not key:
            raise ValueError("Sin GEMINI_API_KEY")
        client = genai.Client(api_key=key)

        prompt = (
            "Sos el community manager de Ahora Noticias, diario digital de Santiago del Estero.\n\n"
            "Generá DOS textos para comunicar la muerte de una figura central del periodismo argentino:\n\n"
            "TITULAR: 'Murió Chiche Gelblung a los 82 años'\n\n"
            "CONTEXTO: Samuel 'Chiche' Gelblung, periodista, conductor y fundador de Minuto Uno, "
            "murió el 9 de septiembre de 2026. Tenía 82 años. Llevaba días internado en el Sanatorio "
            "Mater Dei por una complicación respiratoria. Fue una de las figuras más emblemáticas y "
            "polémicas del periodismo argentino: conductor de 'Memoria' en Canal 9 (el programa "
            "de investigación más visto de los 90), trabajó en Radio Mitre, Radio 10, Radio Rivadavia. "
            "Fundó Minuto Uno en 2006. Era conocido por su estilo directo, sin filtros y su frase "
            "de que quería vivir 200 años.\n\n"
            "TEXTO 1 — Caption Instagram (máx 160 palabras):\n"
            "- Tono: emotivo, respetuoso, que honre su legado sin exagerar\n"
            "- Hook que detenga el scroll con la noticia\n"
            "- Datos clave de su carrera\n"
            "- Cerrá con: #ChicheGelblung #Periodismo #AhoraNoticias #Espectáculos\n\n"
            "TEXTO 2 — Copy Facebook (máx 80 palabras):\n"
            "- Arrancar con la noticia directa\n"
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
            "🖤 MURIÓ CHICHE GELBLUNG\n\n"
            "Samuel 'Chiche' Gelblung, una de las figuras más emblemáticas del periodismo "
            "argentino, falleció este miércoles a los 82 años en el Sanatorio Mater Dei de "
            "Buenos Aires.\n\n"
            "📺 Conductor de 'Memoria' en Canal 9, el ciclo de investigación más visto de los 90.\n"
            "🎙️ Referente en Radio Mitre, Radio 10 y Radio Rivadavia.\n"
            "💻 Fundador de Minuto Uno en 2006.\n\n"
            "El periodismo argentino despide hoy a un grande. Chiche quería vivir 200 años. "
            "Nos dejó a los 82, pero su legado es para siempre.\n\n"
            "#ChicheGelblung #Periodismo #AhoraNoticias #Espectáculos"
        )
        fb = (
            "🖤 MURIÓ CHICHE GELBLUNG a los 82 años. El histórico periodista y fundador de "
            "Minuto Uno falleció este miércoles en Buenos Aires. Conductor de 'Memoria', "
            "referente de la radio y la televisión argentina durante seis décadas. "
            "El periodismo argentino está de luto.\n\n"
            f"Leé la nota completa → {wp_link}"
        )
        return {"instagram": ig, "facebook": fb}


def main():
    database.init_db()

    if database.is_published(URL_CANONICA):
        logger.warning("Esta nota ya fue publicada. Abortando.")
        return

    logger.info("=== Publicando: Muerte de Chiche Gelblung ===")

    # ── IMAGEN ────────────────────────────────────────────────────────────────
    logger.info("Buscando imagen...")
    img_url = _buscar_imagen()
    if not img_url:
        logger.error("Sin imagen. Abortando.")
        return

    # ── WORDPRESS ─────────────────────────────────────────────────────────────
    wp_img_id = None
    try:
        result = wordpress.upload_image(
            image_url=img_url,
            filename=f"chiche-gelblung-{datetime.now().strftime('%Y%m%d')}.jpg",
        )
        if isinstance(result, tuple):
            wp_img_id, _ = result
    except Exception as e:
        logger.warning(f"Imagen WP fallida: {e}")

    cat_ids = []
    for cat in ["Espectáculos", "Sociedad"]:
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
        logger.error("WP no respondió.")
        return

    if isinstance(wp_result, tuple):
        wp_id, wp_link = wp_result
    else:
        wp_id = wp_result.get("id") if isinstance(wp_result, dict) else None
        wp_link = wp_result.get("link", "https://ahoranoticias.com.ar") if isinstance(wp_result, dict) else "https://ahoranoticias.com.ar"

    logger.info(f"✓ WordPress: ID={wp_id} | {wp_link}")

    if wp_id:
        try:
            wordpress.rotate_sticky_posts(new_post_ids=[int(wp_id)], max_sticky=4)
        except Exception as e:
            logger.warning(f"Rotate sticky: {e}")

    database.mark_published(URL_CANONICA, TITULO_WP, FUENTE,
                            wp_post_id=str(wp_id) if wp_id else None)

    # ── CAPTIONS ──────────────────────────────────────────────────────────────
    captions = _generar_captions_gemini(wp_link)
    logger.info(f"\n--- INSTAGRAM ---\n{captions['instagram']}\n")
    logger.info(f"--- FACEBOOK ---\n{captions['facebook']}\n")

    # ── FLYER ─────────────────────────────────────────────────────────────────
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
            categoria=CATEGORIA,
        )
        logger.info("✓ Flyer generado")

        ts = datetime.now().strftime("%Y%m%d%H%M%S")
        upload_result = wordpress.upload_image(flyer_path, f"flyer-gelblung-{ts}.jpg")
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
        logger.error("Sin URL de flyer. Abortando redes.")
        return

    # ── INSTAGRAM ─────────────────────────────────────────────────────────────
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

    # ── FACEBOOK ──────────────────────────────────────────────────────────────
    fb_id = None
    try:
        fb_id = facebook.post_link(
            title=TITULO_WP,
            wp_post_url=wp_link,
            original_url=wp_link,
            image_url=flyer_url,
            caption=captions["facebook"],
        )
        logger.info(f"✓ Facebook: {'ID=' + str(fb_id) if fb_id else 'FALLÓ'}")
    except Exception as e:
        logger.error(f"Error Facebook: {e}")

    logger.info(f"\n{'━'*55}")
    logger.info(f"  WP: {wp_link}")
    logger.info(f"  IG: {ig_id or 'falló'}")
    logger.info(f"  FB: {fb_id or 'falló'}")
    logger.info(f"{'━'*55}")


if __name__ == "__main__":
    main()
