"""
News Auto-Publisher
Monitorea RSS de diarios, reescribe con IA y publica en WordPress, Facebook, Instagram y WhatsApp.
Instagram: cola con scoring de relevancia, publicación en ventanas horarias (6-9h, 12-15h, 21-00h).
"""
import os
import re
import time
import logging
import schedule
import tempfile
import unicodedata
from datetime import datetime

import config
import database
from scraper import fetch_entries, extract_article
from rewriter import rewrite_article, check_watermark
from flyer_generator import generate_flyer
from publishers import wordpress, facebook, instagram, whatsapp

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("autopublisher.log", encoding="utf-8"),
    ],
)
logger = logging.getLogger("main")


# ── Deduplicación semántica por similitud de palabras clave ──────────────────
# Detecta cuando dos artículos de distintas fuentes cubren el mismo tema.

DEDUP_HOURS = 12              # ventana de comparación (horas atrás)
DEDUP_THRESHOLD = 0.38        # similitud Jaccard para duplicado (post-rewrite)
DEDUP_THRESHOLD_PRE = 0.50    # umbral más estricto para pre-filtro (sin gastar API)
MIN_BODY_CHARS = 300          # mínimo de texto en el cuerpo reescrito para publicar
MIN_RELEVANCE_SCORE = 3       # ig_relevancia mínimo para publicar en cualquier canal

_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "en", "con", "por", "para", "que", "segun",
    "se", "lo", "le", "les", "su", "sus", "y", "o", "a", "e",
    "es", "son", "fue", "era", "ha", "han", "hay", "no", "ni",
    "si", "ya", "mas", "pero", "como", "muy", "bien", "aqui",
    "cuando", "donde", "quien", "cual", "cuales", "sobre", "ante",
    "tras", "entre", "durante", "desde", "hasta", "tambien",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "aquel", "todo", "toda", "todos", "todas", "otro", "otra",
    "mismo", "misma", "cada", "nuevo", "nueva", "gran", "solo",
    "tras", "junto", "luego", "pese", "tras", "segun", "ante",
}


def _palabras_clave(titulo: str) -> set[str]:
    """
    Normaliza un título: quita acentos, pasa a minúsculas, descarta
    stopwords y palabras cortas. Devuelve el conjunto de términos clave.
    """
    # Quitar acentos
    sin_tildes = unicodedata.normalize("NFD", titulo)
    sin_tildes = "".join(c for c in sin_tildes if unicodedata.category(c) != "Mn")
    # Minúsculas y quitar puntuación
    limpio = re.sub(r"[^\w\s]", " ", sin_tildes.lower())
    # Palabras significativas: más de 3 chars, no stopword
    return {p for p in limpio.split() if len(p) > 3 and p not in _STOPWORDS_ES}


def _jaccard(titulo_a: str, titulo_b: str) -> float:
    """Similitud Jaccard entre dos títulos sobre sus palabras clave."""
    a = _palabras_clave(titulo_a)
    b = _palabras_clave(titulo_b)
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def es_tema_duplicado(
    nuevo_titulo: str,
    titulos_recientes: list[str],
    umbral: float = DEDUP_THRESHOLD,
) -> tuple[bool, str, float]:
    """
    Compara el nuevo título contra los publicados recientemente.
    Devuelve (es_duplicado, titulo_mas_similar, similitud).
    """
    mejor_sim = 0.0
    mejor_titulo = ""
    for titulo in titulos_recientes:
        sim = _jaccard(nuevo_titulo, titulo)
        if sim > mejor_sim:
            mejor_sim = sim
            mejor_titulo = titulo
    return mejor_sim >= umbral, mejor_titulo, round(mejor_sim, 2)


def _cuerpo_valido(body_html: str) -> bool:
    """Verifica que el cuerpo reescrito tiene contenido real (no es el fallback vacío)."""
    texto = re.sub(r"<[^>]+>", "", body_html or "").strip()
    return len(texto) >= MIN_BODY_CHARS


# ── Filtro de contenido irrelevante por título o URL ─────────────────────────
# Descarta noticias que no tienen valor para una audiencia argentina
# antes de gastar créditos de API en ellas.

_TITULO_SPAM = [
    r"\bgana\s*gato\b",           # lotería mexicana
    r"\bmelate\b",                 # lotería mexicana
    r"\btris\b",                   # lotería mexicana
    r"\bpoblanito\b",
    r"n[uú]meros?\s+ganadores?",   # resultados de sorteos
    r"resultados?\s+(del?|de\s+la)\s+sorteo",
    r"\bboleto\s+ganador\b",
]

# Infobae /america/ cubre toda Latinoamérica — bloqueamos todo ese subdominio.
# Solo nos interesan las secciones argentinas de Infobae.
_INFOBAE_URL_SKIP = [
    r"infobae\.com/america/",   # Toda la cobertura latinoamericana de Infobae
    r"infobae\.com/en/",        # Versión en inglés
]

# Límite de artículos NO argentinos por ciclo completo (todas las fuentes)
MAX_NO_ARGENTINA_POR_CICLO = 2


# Patrones que indican que Cadena 3 está hablando de sí misma
# (sus programas, conductores, eventos propios, publicidades internas)
_CADENA3_AUTOPROMOCIONAL = [
    r"\bcadena\s*3\b",            # menciona "Cadena 3" como protagonista
    r"\bel\s+show\s+del\s+mediod[ií]a\b",
    r"\bv[ií]a\s+pa[ií]s\b",
    r"\bla\s+ma[ñn]ana\s+de\s+cadena\b",
    r"\bprimera\s+tarde\b",
    r"\bariel\s+rod[rí]guez\b",   # conductor emblema de C3
    r"\bnuestro\s+(programa|equipo|conductor)\b",
]


def _es_irrelevante(titulo: str, url: str, source_name: str) -> bool:
    """
    Retorna True si el artículo es claramente irrelevante para la audiencia argentina.
    """
    titulo_lower = titulo.lower()
    for patron in _TITULO_SPAM:
        if re.search(patron, titulo_lower):
            return True
    if source_name == "Infobae":
        for patron in _INFOBAE_URL_SKIP:
            if re.search(patron, url):
                return True
    if source_name == "Cadena 3":
        for patron in _CADENA3_AUTOPROMOCIONAL:
            if re.search(patron, titulo_lower):
                logger.debug(f"  [CADENA3] Contenido propio descartado: {titulo[:60]}")
                return True
    return False


# ── Prioridad geográfica ──────────────────────────────────────────────────────
REGION_PRIORITY = {"Argentina": 0, "Latinoamerica": 1, "Internacional": 2}


def _region_sort_key(item):
    return REGION_PRIORITY.get(item.get("region", "Argentina"), 2)


# ── Ventanas horarias de Instagram ────────────────────────────────────────────
IG_POSTING_WINDOWS = [
    (6, 9),    # 6:00 – 9:00
    (12, 15),  # 12:00 – 15:00
    (21, 24),  # 21:00 – 00:00
]
IG_MAX_PER_RUN = 2      # máximo posts por ciclo de 30 min dentro de una ventana
IG_DAILY_LIMIT = 50     # límite real de la API de Meta
IG_RELEVANCE_MIN = 7    # puntaje mínimo para fuentes generales
IG_RELEVANCE_MIN_MUNICIPAL = 4   # umbral más bajo para municipios anunciantes
IG_MUNICIPAL_SOURCES = {"Santiago Ciudad", "Municipalidad La Banda"}


def _is_ig_window() -> bool:
    """Devuelve True si el horario actual cae en una ventana de publicación IG."""
    hora = datetime.now().hour
    return any(start <= hora < end for start, end in IG_POSTING_WINDOWS)


# ── Procesamiento de fuentes ──────────────────────────────────────────────────

def process_source(source: dict, titulos_recientes: list[str], no_argentina_count: list = None):
    """
    titulos_recientes: lista compartida entre fuentes del mismo ciclo.
    Se actualiza en el lugar con cada nota nueva publicada, para que
    la segunda fuente no repita un tema que la primera ya cubrió.
    """
    logger.info(f"Procesando fuente: {source['name']}")
    entries = fetch_entries(source, max_items=source.get("max_articles", config.MAX_ARTICLES_PER_RUN))

    # Pre-procesar con pipeline de filtros. Solo los artículos que pasan todos
    # los filtros se agregan a `pending` para ser publicados.
    pending = []
    for entry in entries:
        url = entry["url"]
        if not url:
            continue
        if database.is_published(url):
            logger.debug(f"Ya publicado: {url}")
            continue

        logger.info(f"Nueva noticia: {entry['title'][:80]}")

        # ── FILTRO 1: contenido irrelevante por título/URL (sin costo de API) ──
        if _es_irrelevante(entry["title"], url, source["name"]):
            logger.info(f"  [IRRELEVANTE] Descartado por título/URL: {entry['title'][:70]}")
            database.mark_seen(url, entry["title"], source["name"])
            continue

        # ── FILTRO 2: dedup rápido con título original (sin costo de API) ──────
        dup_pre, titulo_sim_pre, sim_pre = es_tema_duplicado(
            entry["title"], titulos_recientes, umbral=DEDUP_THRESHOLD_PRE
        )
        if dup_pre:
            logger.info(
                f"  [PRE-DEDUP] Tema ya cubierto (sim={sim_pre}) — saltando sin reescribir:\n"
                f"    NUEVO:     {entry['title'][:70]}\n"
                f"    YA EXISTE: {titulo_sim_pre[:70]}"
            )
            database.mark_seen(url, entry["title"], source["name"])
            continue

        # ── FILTRO 3: extraer artículo y verificar contenido suficiente ─────────
        # Si la fuente ya provee full_text (ej: La Banda API), lo pasa directo
        article = extract_article(
            url, source["name"], entry["title"], entry["summary"],
            full_text=entry.get("full_text"),
            image_url=entry.get("image_url"),
        )
        if not article:
            logger.warning(f"  [CONTENIDO] Insuficiente o error al extraer: {url}")
            database.mark_seen(url, entry["title"], source["name"])
            continue

        # ── FILTRO 4: reescribir con Claude (incluye evaluación de publicabilidad) ─
        rewritten = rewrite_article(article.title, article.full_text, source["name"])

        # ── FILTRO 5: gate principal — Claude decidió si el contenido es válido ──
        # Cubre: texto truncado, paywall, loterías, sin suficiente información, etc.
        # El fallback del rewriter TAMBIÉN retorna es_publicable=False en caso de error,
        # así nunca se publica texto crudo del diario original.
        if not rewritten.get("es_publicable", False):
            logger.info(
                f"  [NO PUBLICABLE] Claude rechazó el contenido: "
                f"{(rewritten.get('title') or entry['title'])[:70]}"
            )
            database.mark_seen(url, rewritten.get("title") or entry["title"], source["name"])
            continue

        # ── FILTRO 6: segunda capa — cuerpo mínimo 300 chars ─────────────────────
        if not _cuerpo_valido(rewritten["body_html"]):
            logger.warning(
                f"  [CUERPO] Contenido insuficiente tras reescritura — saltando: "
                f"{rewritten['title'][:70]}"
            )
            database.mark_seen(url, rewritten["title"], source["name"])
            continue

        # ── FILTRO 7: relevancia mínima para publicar en cualquier canal ──────────
        if rewritten.get("ig_relevancia", 5) < MIN_RELEVANCE_SCORE:
            logger.info(
                f"  [RELEVANCIA] Score {rewritten.get('ig_relevancia')}/10 muy bajo — no se publica: "
                f"{rewritten['title'][:70]}"
            )
            database.mark_seen(url, rewritten["title"], source["name"])
            continue

        # ── FILTRO 8: dedup semántico con título reescrito (más preciso) ─────────
        duplicado, titulo_similar, similitud = es_tema_duplicado(
            rewritten["title"], titulos_recientes
        )
        if duplicado:
            logger.info(
                f"  [POST-DEDUP] Tema repetido (sim={similitud}) — saltando:\n"
                f"    NUEVO:     {rewritten['title'][:70]}\n"
                f"    YA EXISTE: {titulo_similar[:70]}"
            )
            database.mark_seen(url, rewritten["title"], source["name"])
            continue

        region = rewritten.get("region", "Argentina")

        # ── FILTRO: límite de artículos no-argentinos por ciclo ───────────────
        if region != "Argentina" and no_argentina_count is not None:
            if no_argentina_count[0] >= MAX_NO_ARGENTINA_POR_CICLO:
                logger.info(
                    f"  [CUOTA] Límite no-Argentina alcanzado ({MAX_NO_ARGENTINA_POR_CICLO}) "
                    f"— saltando: {rewritten['title'][:60]}"
                )
                database.mark_seen(url, rewritten["title"], source["name"])
                continue

        pending.append({
            "url": url,
            "article": article,
            "rewritten": rewritten,
            "region": region,
        })

    # Ordenar por región: Argentina > Latinoamérica > Internacional
    pending.sort(key=_region_sort_key)
    if pending:
        logger.info(f"  → Orden: {[p['region'] for p in pending]}")

    processed = 0
    for item in pending:
        url = item["url"]
        article = item["article"]
        rewritten = item["rewritten"]
        categoria = rewritten.get("categoria", "")
        ig_score = rewritten.get("ig_relevancia", 5)

        # 1. Verificar marca de agua
        imagen_limpia = article.image_url
        if imagen_limpia and check_watermark(imagen_limpia):
            logger.info(f"Imagen descartada por marca de agua: {imagen_limpia}")
            imagen_limpia = None

        # 2. Subir foto original a WordPress como imagen destacada
        wp_post_id = None
        wp_post_url = None
        media_id = None
        media_url = None   # URL pública de la imagen en WordPress

        if imagen_limpia:
            media_id, media_url = wordpress.upload_image(
                image_url=imagen_limpia,
                filename=f"foto-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
            )

        # 3. Publicar en WordPress
        wp_post_id, wp_post_url = wordpress.create_post(
            title=rewritten["title"],
            body_html=rewritten["body_html"],
            original_url=url,
            source_name=source["name"],
            featured_media_id=media_id,
        )

        # 4. Publicar en Facebook
        # Usamos media_url (imagen ya subida a WP) para garantizar que Facebook
        # siempre muestre la imagen correcta. Evita que Infobae/otros bloqueen
        # el hotlink y evita el logo genérico del sitio.
        fb_image = media_url or imagen_limpia
        fb_post_id = facebook.post_link(
            title=rewritten["title"],
            wp_post_url=wp_post_url or url,
            original_url=url,
            image_url=fb_image,
        )

        # 5. Generar flyer y encolar en Instagram
        # Municipios anunciantes tienen umbral más bajo para garantizar presencia diaria
        flyer_public_url = None
        flyer_path = None
        ig_encolado = False
        es_municipal = source["name"] in IG_MUNICIPAL_SOURCES
        ig_min = IG_RELEVANCE_MIN_MUNICIPAL if es_municipal else IG_RELEVANCE_MIN

        if ig_score >= ig_min:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                flyer_path = tmp.name
            try:
                generate_flyer(
                    title=rewritten["title"],
                    source_name=source["name"],
                    article_image_url=imagen_limpia,
                    template_path=config.FLYER_TEMPLATE_PATH,
                    output_path=flyer_path,
                    categoria=categoria,
                )
                # Subir flyer a WP para tener URL pública persistente
                _, flyer_public_url = wordpress.upload_image(
                    image_path=flyer_path,
                    filename=f"flyer-{datetime.now().strftime('%Y%m%d%H%M%S')}.jpg",
                )
                # Agregar a la cola de Instagram
                added = database.ig_queue_add(
                    url=url,
                    title=rewritten["title"],
                    ig_caption=rewritten["instagram_caption"],
                    flyer_public_url=flyer_public_url,
                    relevance_score=ig_score,
                    source=source["name"],
                )
                ig_encolado = added
                logger.info(
                    f"  → IG cola: score={ig_score}/10 | "
                    f"{'encolado ✓' if added else 'ya en cola'} | "
                    f"pendientes={database.ig_queue_count_pending()}"
                )
            except Exception as e:
                logger.error(f"Error generando flyer para IG: {e}")
            finally:
                if flyer_path and os.path.exists(flyer_path):
                    try:
                        os.unlink(flyer_path)
                    except Exception:
                        pass
        else:
            logger.info(f"  → IG omitido: score={ig_score}/10 (mínimo {IG_RELEVANCE_MIN})")

        # 6. WhatsApp
        wa_sent = whatsapp.send_to_channel(
            text=rewritten["whatsapp_text"],
            wp_post_url=wp_post_url,
        )

        # 7. Registrar en DB (ig_post_id se completará después cuando se publique)
        database.mark_published(
            url=url,
            title=rewritten["title"],
            source=source["name"],
            wp_post_id=str(wp_post_id) if wp_post_id else None,
            fb_post_id=str(fb_post_id) if fb_post_id else None,
            ig_post_id=None,  # se asignará al publicar desde la cola
            wa_sent=wa_sent,
        )

        logger.info(
            f"✓ Publicado: WP={wp_post_id} | FB={fb_post_id} | "
            f"IG={'en cola' if ig_encolado else 'omitido'} | WA={wa_sent}"
        )
        # Agregar título a lista compartida para dedup entre fuentes
        titulos_recientes.append(rewritten["title"])

        # Contar artículos no-argentinos publicados en este ciclo
        if rewritten.get("region", "Argentina") != "Argentina" and no_argentina_count is not None:
            no_argentina_count[0] += 1

        processed += 1
        time.sleep(5)

    logger.info(f"  → {source['name']}: {processed} artículos nuevos publicados")


# ── Publicación desde cola de Instagram ──────────────────────────────────────

def publish_ig_queue():
    """
    Si estamos en una ventana horaria de IG, publica los artículos más relevantes
    de la cola. Máximo IG_MAX_PER_RUN por ciclo. Respeta el límite diario.
    """
    if not _is_ig_window():
        logger.debug("Fuera de ventana horaria de Instagram. Cola en espera.")
        return

    posts_hoy = database.ig_queue_count_today()
    restantes_dia = IG_DAILY_LIMIT - posts_hoy
    if restantes_dia <= 0:
        logger.warning(f"Instagram: límite diario alcanzado ({posts_hoy}/{IG_DAILY_LIMIT}).")
        return

    a_publicar = min(IG_MAX_PER_RUN, restantes_dia)
    pendientes = database.ig_queue_get_pending(limit=a_publicar)

    if not pendientes:
        logger.info("Cola de Instagram vacía en esta ventana.")
        return

    hora_actual = datetime.now().strftime("%H:%M")
    logger.info(
        f"Ventana IG activa ({hora_actual}) | "
        f"hoy={posts_hoy}/{IG_DAILY_LIMIT} | "
        f"publicando {len(pendientes)} de {database.ig_queue_count_pending()} pendientes"
    )

    for item in pendientes:
        ig_post_id = instagram.post_image(
            image_path=None,
            caption=item["ig_caption"],
            public_image_url=item["flyer_public_url"],
        )
        if ig_post_id:
            database.ig_queue_mark_posted(item["original_url"], ig_post_id)
            logger.info(
                f"  ✓ IG publicado: {item['title'][:60]} "
                f"(score={item['relevance_score']}) ID={ig_post_id}"
            )
        else:
            logger.warning(f"  ✗ IG falló: {item['title'][:60]}")
        time.sleep(4)


# ── Ciclo principal ───────────────────────────────────────────────────────────

def run_cycle():
    logger.info("=" * 60)
    logger.info(f"Iniciando ciclo: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    titulos_recientes = database.get_recent_titles(hours=DEDUP_HOURS)
    logger.info(f"Deduplicador cargado: {len(titulos_recientes)} títulos de las últimas {DEDUP_HOURS}h")

    # Contador compartido de artículos NO argentinos publicados en este ciclo.
    # Las fuentes municipales y El Liberal son siempre argentinas.
    # Infobae y Cadena 3 pueden traer contenido internacional.
    no_argentina_count = [0]   # lista para mutabilidad en process_source

    # 1. Procesar todas las fuentes (WP + FB + encolar IG si relevante)
    for source in config.NEWS_SOURCES:
        try:
            process_source(source, titulos_recientes, no_argentina_count)
        except Exception as e:
            logger.error(f"Error procesando {source['name']}: {e}")
        time.sleep(3)

    logger.info(f"Ciclo: {no_argentina_count[0]} artículos no-argentinos publicados (máx {MAX_NO_ARGENTINA_POR_CICLO})")

    # 2. Publicar desde cola de Instagram si es horario activo
    publish_ig_queue()

    logger.info("Ciclo finalizado.")


def main():
    logger.info("News Auto-Publisher iniciado.")
    database.init_db()

    run_cycle()

    schedule.every(config.CHECK_INTERVAL_MINUTES).minutes.do(run_cycle)
    logger.info(f"Corriendo cada {config.CHECK_INTERVAL_MINUTES} minutos...")

    while True:
        schedule.run_pending()
        time.sleep(30)


if __name__ == "__main__":
    main()
