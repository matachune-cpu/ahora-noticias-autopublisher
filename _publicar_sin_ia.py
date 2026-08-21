"""
Publicación directa a WordPress sin IA.
Modo de emergencia cuando Gemini tiene cuota agotada.

Flujo:
  1. Scrapea artículos de todas las fuentes configuradas
  2. Filtra URLs con segmentos claramente internacionales
  3. Detecta categoría temática por palabras clave del título
  4. Publica en WP con categoría asignada y texto original limpio
  5. Rota los sticky posts del encabezado con los nuevos artículos
  6. Omite completamente Facebook, Instagram y WhatsApp

Uso:
    python _publicar_sin_ia.py [--max 10]
"""
import argparse
import logging
import re
import time
import unicodedata
from datetime import datetime

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

load_dotenv()

import config
import database
from scraper import fetch_entries, extract_article
from publishers import wordpress

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("publicar_sin_ia")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept-Language": "es-AR,es;q=0.9",
}

MIN_CHARS = 300
DEDUP_THRESHOLD = 0.45
DEDUP_HOURS = 12
MAX_POR_PROVINCIA = 1  # máximo artículos por provincia por tanda

# Segmentos de URL que indican contenido internacional
_URL_INTERNACIONAL = (
    "/el-mundo/", "/mundo/", "/internacional/", "/world/",
    "/eeuu/", "/usa/", "/trump/", "/biden/",
    "/europa/", "/asia/", "/africa/",
    "/america/eeuu", "/america/mexico", "/america/colombia",
    "/america/venezuela", "/america/brasil", "/america/peru",
    "/america/chile", "/america/bolivia", "/america/ecuador",
    "/america/cuba", "/america/nicaragua", "/america/haiti",
    "/america/dominicana", "/america/guatemala", "/america/honduras",
    "/america/salvador", "/america/costa-rica", "/america/panama",
    "/america/uruguay", "/america/paraguay",
)

# Palabras clave en títulos que revelan contenido internacional
_TITULO_INTERNACIONAL = (
    # Latinoamérica — ciudades y países
    "lima", "ciudad de méxico", "ciudad de mexico",
    "bogotá", "bogota", "santiago de chile", "caracas",
    "la paz", "quito", "montevideo", "asunción", "asuncion",
    "río de janeiro", "rio de janeiro", "sao paulo", "brasilia",
    " méxico ", " mexico ", " perú ", " peru ", " colombia ",
    " bolivia ", " ecuador ", " venezuela ", " brasil ", " brazil ",
    " cuba ", " uruguay ", " paraguay ", " chile ", " panamá ", " panama ",
    " guatemala ", " honduras ", " nicaragua ", " haití ", " haiti ",
    "gobierno de méxico", "gobierno de chile", "gobierno de colombia",
    "presidente de méxico", "presidente de brasil", "presidente de chile",
    # España — política, partidos, ciudades
    " españa ", " espana ", "madrid", "barcelona", "ceuta", "melilla",
    "sevilla", "valencia", "bilbao", "zaragoza", "paterna",
    "cataluña", "cataluna", "euskadi", "país vasco",
    "pedro sánchez", "pedro sanchez", "partido popular", "partido socialista",
    " psoe", " pp avisa", " pp pide", " vox ", "podemos ", "sumar ",
    "congreso de los diputados", "gobierno español", "gobierno de españa",
    "generalitat", "comunidad de madrid",
    # Fútbol y deportes europeos/españoles
    "real madrid", "atlético de madrid", "atletico de madrid",
    "fc barcelona", "athletic bilbao", "real betis", "sevilla fc",
    "valencia cf", "villarreal", "osasuna", "getafe", "espanyol",
    "corberán", "corberan", "ancelotti", "flick ", "simeone",
    # F1 — pilotos y equipos europeos (sin contexto argentino)
    "sainz", "albon", "williams f1", "ferrari f1", "red bull f1",
    "norris", "piastri", "verstappen", "leclerc", "russell ",
    # Resto de Europa y mundo
    "paris", "berlín", "berlin", "roma", "londres", "bruselas",
    "tokio", "tokyo", "beijing", "moscú", "moscu", "tel aviv", "gaza",
    " francia ", " alemania ", " italia ", " china ", " rusia ",
    " ucrania ", " israel ", " turquía ", " turquia ",
    "nueva york", "new york", "washington", "los ángeles", "los angeles", "miami",
    # EEUU
    "estados unidos", "eeuu", "trump", "biden", "harris", "casa blanca",
)

# Si el resumen contiene "(EFE).-" y no menciona Argentina → internacional
_ARGENTINA_MENTIONS = (
    "argentina", "buenos aires", "córdoba", "mendoza", "rosario",
    "santiago del estero", "tucumán", "salta", "jujuy", "neuquén",
    "corrientes", "chaco", "misiones", "entre ríos", "santa fe",
    "la pampa", "san juan", "san luis", "río negro", "chubut",
    "santa cruz", "tierra del fuego", "formosa", "catamarca", "la rioja",
)

# Categorías donde se permite contenido internacional
_CATEGORIAS_INTL_PERMITIDAS = {"Espectáculos", "Tecnología"}

# Señales en URLs de imágenes que indican que es un logo genérico y no una foto
_LOGO_URL_SIGNALS = (
    "logo", "default-image", "placeholder", "no-image", "noimage",
    "default_image", "favicon", "apple-touch", "og-default", "share-default",
    "brand/", "/brand-", "watermark",
)

# Detección de categoría por palabras clave en el título (orden de prioridad)
_CATEGORIAS_KW = [
    ("Espectáculos", [
        "actor", "actriz", "cantante", "celebridad", "famoso", "famosa",
        "telenovela", "reality", "gran hermano", "got talent", "masterchef",
        "grammy", "oscar", "emmy", "golden globe", "alfombra roja",
        "netflix", "disney", "amazon prime", "hbo", "star plus",
        "farándula", "farandula", "escándalo", "ruptura", "separación",
        "boda", "embarazo", "influencer", "youtuber", "tiktoker",
        "taylor swift", "bad bunny", "shakira", "daddy yankee",
        "ricky martin", "j balvin", "maluma", "karol g",
        "wanda nara", "pampita", "marcelo tinelli", "susana giménez",
        "mirtha legrand", "julio iglesias", "madonna",
    ]),
    ("Deportes", [
        "fútbol", "futbol", "gol", "river", "boca", "racing", "independiente",
        "belgrano", "san lorenzo", "estudiantes", "selección", "mundial",
        "copa", "torneo", "partido", "jugador", "deporte", "tenis", "basquet",
        "atletismo", "natación", "ciclismo", "boxeo", "mma", "maratón",
        "olimp", "nba", "formula 1", "moto gp",
    ]),
    ("Economía", [
        "dólar", "dolar", "inflación", "inflacion", "precio", "mercado",
        "banco", "economía", "economia", "presupuesto", "inversión", "inversion",
        "finanzas", "pbi", "reservas", "deuda", "bono", "indec", "canasta",
        "tarifas", "combustible", "nafta", "sueldo", "salario", "jubilación",
        "jubilacion", "exportación", "importación", "aduana", "impo", "expo",
        "bolsa", "acciones", "interés", "interes", "tipo de cambio",
    ]),
    ("Política", [
        "presidente", "gobierno", "congreso", "senado", "diputado", "ministro",
        "elección", "elecciones", "milei", "kirchner", "peronismo", "peronista",
        "gobernador", "intendente", "legislatura", "decreto", "ley", "proyecto",
        "partido", "oposición", "oposicion", "oficialismo", "coalición",
        "candidato", "cambiemos", "unión por la patria", "la libertad avanza",
        "pro ", " ucr", "kicillof", "massa", "bullrich", "larreta",
    ]),
    ("Seguridad", [
        "policia", "policía", "crimen", "robo", "homicidio", "narco",
        "detenido", "preso", "cárcel", "carcel", "asesinato", "accidente",
        "incendio", "siniestro", "víctima", "victima", "violencia", "femicidio",
        "secuestro", "extorsión", "banda", "delito", "tráfico", "contrabando",
        "allanamiento", "operativo", "gendarmería", "prefectura",
    ]),
    ("Salud", [
        "salud", "hospital", "médico", "medico", "enfermedad", "vacuna",
        "covid", "dengue", "gripe", "pandemia", "tratamiento", "paciente",
        "cirugía", "cirugia", "cáncer", "cancer", "diabetes", "obesidad",
        "obra social", "pami", "medicamento", "farmacia", "clínica",
    ]),
    ("Cultura", [
        "cultura", "arte", "cine", "teatro", "música", "musica", "festival",
        "libro", "exposición", "exposicion", "artista", "recital", "show",
        "película", "pelicula", "serie", "carnaval", "patrimonio",
    ]),
    ("Tecnología", [
        "tecnología", "tecnologia", "app", "inteligencia artificial", "internet",
        "digital", "software", "startup", "innovación", "innovacion", "robot",
        "satélite", "satelite", "ciberseguridad", "hacker", "redes sociales",
    ]),
    ("Medio Ambiente", [
        "clima", "ambiente", "ecología", "ecologia", "inundación", "inundacion",
        "sequía", "sequia", "contaminación", "contaminacion", "biodiversidad",
        "energía renovable", "energia renovable", "solar", "eólica", "eolica",
        "bosque", "incendio forestal", "glaciar", "reciclaje",
    ]),
    ("Sociedad", []),  # fallback
]

# Santiago del Estero es la base del sitio, no necesita prefijo de provincia
_PROVINCIAS_SIN_PREFIJO = {"Santiago del Estero"}


def _titulo_con_provincia(title: str, provincia: str) -> str:
    """Integra la provincia en el título de forma natural en redacción periodística."""
    if not provincia or provincia in _PROVINCIAS_SIN_PREFIJO:
        return title
    # Bajar la primera letra para que la oración fluya naturalmente
    resto = title[0].lower() + title[1:] if title and title[0].isupper() else title
    return f"En {provincia}, {resto}"


_STOPWORDS = {
    "el","la","los","las","un","una","de","del","al","en","con","por","para",
    "que","se","lo","le","y","o","a","es","son","fue","ha","hay","no","si",
    "ya","pero","como","este","esta","ese","esa","todo","cada","nuevo","nueva",
}

# Cache de IDs de categorías WP para no consultar en cada artículo
_categoria_id_cache: dict[str, int] = {}


def _palabras(titulo: str) -> set:
    s = unicodedata.normalize("NFD", titulo)
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    s = re.sub(r"[^\w\s]", " ", s.lower())
    return {p for p in s.split() if len(p) > 3 and p not in _STOPWORDS}


def _jaccard(a: str, b: str) -> float:
    wa, wb = _palabras(a), _palabras(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _es_duplicado(titulo: str, recientes: list[str]) -> bool:
    return any(_jaccard(titulo, t) >= DEDUP_THRESHOLD for t in recientes)


def _es_internacional(url: str, title: str, summary: str = "") -> bool:
    """Detecta contenido internacional por URL, título o resumen de agencia EFE."""
    url_lower = url.lower()
    if any(seg in url_lower for seg in _URL_INTERNACIONAL):
        return True
    title_lower = f" {title.lower()} "
    if any(kw in title_lower for kw in _TITULO_INTERNACIONAL):
        return True
    # Agencia EFE (española): si el resumen contiene (EFE) y no menciona Argentina
    summary_lower = summary.lower()
    if "(efe)" in summary_lower:
        combined = title_lower + " " + summary_lower
        if not any(arg in combined for arg in _ARGENTINA_MENTIONS):
            return True
    return False


def _imagen_es_logo(url: str) -> bool:
    """Detecta si la URL de la imagen es un logo genérico del medio."""
    if not url:
        return True
    url_lower = url.lower()
    return any(s in url_lower for s in _LOGO_URL_SIGNALS)


def _detectar_categoria(title: str) -> str:
    title_lower = title.lower()
    for categoria, keywords in _CATEGORIAS_KW:
        if any(kw in title_lower for kw in keywords):
            return categoria
    return "Sociedad"


def _get_categoria_id(nombre: str) -> int | None:
    if nombre in _categoria_id_cache:
        return _categoria_id_cache[nombre]
    cat_id = wordpress.get_or_create_category(nombre)
    if cat_id:
        _categoria_id_cache[nombre] = cat_id
    return cat_id


def _get_og_image(url: str) -> str | None:
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        for prop in ["og:image", "twitter:image"]:
            tag = soup.find("meta", property=prop) or soup.find("meta", attrs={"name": prop})
            if tag and tag.get("content"):
                return tag["content"]
    except Exception:
        pass
    return None


def _build_body_html(text: str, source_name: str, original_url: str) -> str:
    parrafos = [p.strip() for p in text.split("\n") if len(p.strip()) > 40]
    if not parrafos:
        parrafos = [text.strip()]
    cuerpo = "\n".join(f"<p>{p}</p>" for p in parrafos[:18])
    pie = (
        f'<p><em>Fuente original: '
        f'<a href="{original_url}" target="_blank" rel="noopener">{source_name}</a></em></p>'
    )
    return cuerpo + "\n" + pie


def run(max_articles: int = 10):
    database.init_db()
    logger.info(f"=== Publicación sin IA — máx {max_articles} artículos ===")

    titulos_recientes = database.get_recent_titles(hours=DEDUP_HOURS)
    logger.info(f"Deduplicador: {len(titulos_recientes)} títulos en últimas {DEDUP_HOURS}h")

    publicados = 0
    nuevos_ids = []
    provincia_count: dict[str, int] = {}  # artículos publicados por provincia esta tanda

    for source in config.NEWS_SOURCES:
        if publicados >= max_articles:
            break

        provincia = source.get("provincia", "")
        if provincia and provincia_count.get(provincia, 0) >= MAX_POR_PROVINCIA:
            logger.info(f"  [PROV LIMIT] {provincia}: ya publicado 1 artículo esta tanda, saltando")
            continue

        logger.info(f"Fuente: {source['name']}")
        entries = fetch_entries(source, max_items=source.get("max_articles", 5))

        for entry in entries:
            if publicados >= max_articles:
                break

            url = entry.get("url", "").strip()
            title = entry.get("title", "").strip()

            if not url or len(title) < 10:
                continue

            summary = entry.get("summary", "")

            # Filtro internacional: URL + palabras clave en título + agencia EFE
            if _es_internacional(url, title, summary):
                cat_temp = _detectar_categoria(title)
                if cat_temp not in _CATEGORIAS_INTL_PERMITIDAS:
                    logger.info(f"  [INTL BLOCK] [{cat_temp}] {title[:55]}")
                    database.mark_seen(url, title, source["name"])
                    continue
                logger.info(f"  [INTL OK] [{cat_temp}] {title[:55]}")

            if database.is_published(url):
                continue
            if _es_duplicado(title, titulos_recientes):
                logger.info(f"  [DEDUP] {title[:60]}")
                database.mark_seen(url, title, source["name"])
                continue

            article = extract_article(
                url, source["name"], title, summary,
                full_text=entry.get("full_text"),
                image_url=entry.get("image_url"),
            )
            if not article or len((article.full_text or "").strip()) < MIN_CHARS:
                database.mark_seen(url, title, source["name"])
                continue

            # Imagen: usar la del artículo o buscar og:image, descartando logos
            image_url = article.image_url or _get_og_image(url)
            if _imagen_es_logo(image_url):
                logger.info(f"  Imagen descartada (logo genérico): {(image_url or '')[:60]}")
                image_url = None

            media_id = None
            if image_url:
                try:
                    media_id, _ = wordpress.upload_image(
                        image_url=image_url,
                        filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
                    )
                except Exception as e:
                    logger.warning(f"  Imagen no se pudo subir: {e}")

            # Categoría: nombre de provincia para fuentes locales; tema para nacionales
            if provincia:
                categoria_nombre = provincia
            else:
                categoria_nombre = _detectar_categoria(title)
            cat_id = _get_categoria_id(categoria_nombre)
            categories = [cat_id] if cat_id else []

            # Título con provincia integrada en redacción natural
            titulo_final = _titulo_con_provincia(title, provincia)

            body_html = _build_body_html(article.full_text, source["name"], url)

            try:
                wp_post_id, wp_post_url = wordpress.create_post(
                    title=titulo_final,
                    body_html=body_html,
                    original_url=url,
                    source_name=source["name"],
                    featured_media_id=media_id,
                    categories=categories,
                )
            except Exception as e:
                logger.error(f"  WP error: {e}")
                database.mark_seen(url, title, source["name"])
                continue

            if wp_post_id:
                database.mark_published(url=url, title=title, source=source["name"],
                                        wp_post_id=str(wp_post_id))
                titulos_recientes.append(title)
                nuevos_ids.append(int(wp_post_id))
                publicados += 1
                if provincia:
                    provincia_count[provincia] = provincia_count.get(provincia, 0) + 1
                logger.info(
                    f"  ✓ [{provincia or 'Nacional'}] [{categoria_nombre}] {titulo_final[:60]} | WP ID={wp_post_id}"
                )
            else:
                database.mark_seen(url, title, source["name"])

            time.sleep(2)

        time.sleep(2)

    logger.info(f"=== Completado: {publicados} publicados ===")

    if nuevos_ids:
        logger.info(f"Actualizando encabezado: {len(nuevos_ids)} artículo(s) nuevos → sticky (máx 4)")
        wordpress.rotate_sticky_posts(nuevos_ids, max_sticky=4)

    return publicados


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--max", type=int, default=10,
                        help="Máximo de artículos a publicar (default: 10)")
    args = parser.parse_args()
    run(args.max)
