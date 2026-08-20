import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Google Custom Search API — para búsqueda de imágenes ilustrativas de fallback
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY", "")
GOOGLE_SEARCH_CX = os.getenv("GOOGLE_SEARCH_CX", "")

WP_URL = os.getenv("WP_URL", "").rstrip("/")
WP_USERNAME = os.getenv("WP_USERNAME")
WP_APP_PASSWORD = os.getenv("WP_APP_PASSWORD")

META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN")
FB_PAGE_ID = os.getenv("FB_PAGE_ID")
IG_ACCOUNT_ID = os.getenv("IG_ACCOUNT_ID")

WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID")
WA_CHANNEL_ID = os.getenv("WA_CHANNEL_ID")
WA_API_TOKEN = os.getenv("WA_API_TOKEN")

CHECK_INTERVAL_MINUTES = int(os.getenv("CHECK_INTERVAL_MINUTES", "30"))
MAX_ARTICLES_PER_RUN = int(os.getenv("MAX_ARTICLES_PER_RUN", "5"))
FLYER_TEMPLATE_PATH = os.getenv("FLYER_TEMPLATE_PATH", "templates/flyer_base.png")

NEWS_SOURCES = [
    # ════════════════════════════════════════════════════════════════
    # FUENTES LOCALES — Santiago del Estero (always_include)
    # ════════════════════════════════════════════════════════════════
    {
        "name": "El Liberal",
        "rss": None,
        "url": "https://www.elliberal.com.ar",
        "scrape_links": True,
        "article_selector": "a[href*='/nota/']",
        "max_articles": 5,
        "always_include": True,
        "provincia": "Santiago del Estero",
    },
    {
        "name": "Gobierno SDE",
        "sde_gobierno": True,
        "url": "https://sde.gob.ar/noticias/",
        "max_articles": 3,
        "always_include": True,
        "provincia": "Santiago del Estero",
    },
    {
        "name": "Santiago Ciudad",
        "santiago_ciudad": True,
        "url": "https://www.santiagociudad.gov.ar/noticias",
        "max_articles": 3,
        "always_include": True,
        "provincia": "Santiago del Estero",
    },
    {
        "name": "Municipalidad La Banda",
        "labanda_api": "https://labanda.gob.ar/api/prensa/find-all-news",
        "url": "https://labanda.gob.ar/todas-las-noticias/",
        "max_articles": 3,
        "always_include": True,
        "provincia": "Santiago del Estero",
    },

    # ════════════════════════════════════════════════════════════════
    # NACIONAL — agenda prioritaria Argentina
    # ════════════════════════════════════════════════════════════════
    {
        "name": "Infobae",
        "rss": "https://www.infobae.com/arc/outboundfeeds/rss/",
        "url": "https://www.infobae.com",
        "scrape_links": False,
        "max_articles": 5,
    },
    {
        "name": "La Nación",
        "rss": "https://www.lanacion.com.ar/arc/outboundfeeds/rss/",
        "url": "https://www.lanacion.com.ar",
        "scrape_links": False,
        "max_articles": 4,
    },

    # ════════════════════════════════════════════════════════════════
    # ECONOMÍA ARGENTINA — dólar, inflación, finanzas
    # ════════════════════════════════════════════════════════════════
    {
        "name": "Ámbito Financiero",
        "rss": "https://www.ambito.com/rss.xml",
        "url": "https://www.ambito.com",
        "scrape_links": False,
        "max_articles": 3,
    },
    {
        "name": "El Cronista",
        "rss": "https://www.cronista.com/rss/ultimas-noticias.xml",
        "url": "https://www.cronista.com",
        "scrape_links": False,
        "max_articles": 2,
    },

    # ════════════════════════════════════════════════════════════════
    # PROVINCIAS ARGENTINAS — un diario destacado por provincia
    # ════════════════════════════════════════════════════════════════

    # Buenos Aires (provincia)
    {
        "name": "Diario Hoy",
        "rss": "https://www.diariohoy.net/feed/",
        "url": "https://www.diariohoy.net",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Buenos Aires",
    },

    # CABA
    {
        "name": "Clarín",
        "rss": "https://www.clarin.com/rss/lo-ultimo/",
        "url": "https://www.clarin.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "CABA",
    },

    # Córdoba
    {
        "name": "La Voz del Interior",
        "rss": "https://www.lavoz.com.ar/feed/",
        "url": "https://www.lavoz.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Córdoba",
    },
    {
        "name": "Cadena 3",
        "rss": None,
        "url": "https://www.cadena3.com",
        "scrape_links": True,
        "article_selector": "a[href*='/noticia/']",
        "max_articles": 2,
        "provincia": "Córdoba",
    },

    # Mendoza
    {
        "name": "Los Andes",
        "rss": "https://www.losandes.com.ar/feed/",
        "url": "https://www.losandes.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Mendoza",
    },

    # Santa Fe
    {
        "name": "La Capital",
        "rss": "https://www.lacapital.com.ar/rss/",
        "url": "https://www.lacapital.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Santa Fe",
    },

    # Tucumán
    {
        "name": "La Gaceta",
        "rss": "https://www.lagaceta.com.ar/rss/",
        "url": "https://www.lagaceta.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Tucumán",
    },

    # Salta
    {
        "name": "El Tribuno",
        "rss": "https://www.eltribuno.com/salta/feed",
        "url": "https://www.eltribuno.com/salta",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Salta",
    },

    # Jujuy
    {
        "name": "Jujuy al Momento",
        "rss": "https://www.jujuyalmomento.com/feed/",
        "url": "https://www.jujuyalmomento.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Jujuy",
    },

    # Misiones
    {
        "name": "El Territorio",
        "rss": "https://www.territoriodigital.com/feed/",
        "url": "https://www.territoriodigital.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Misiones",
    },

    # Chaco
    {
        "name": "Chaco Día por Día",
        "rss": "https://www.chacodiapordia.com/feed/",
        "url": "https://www.chacodiapordia.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Chaco",
    },

    # Corrientes
    {
        "name": "Diario Época",
        "rss": "https://www.diarioepoca.com/feed/",
        "url": "https://www.diarioepoca.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Corrientes",
    },

    # Entre Ríos
    {
        "name": "El Diario Entre Ríos",
        "rss": "https://www.eldiario.com.ar/feed/",
        "url": "https://www.eldiario.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Entre Ríos",
    },

    # Formosa
    {
        "name": "La Mañana de Formosa",
        "rss": "https://www.lamananaformosa.com/feed/",
        "url": "https://www.lamananaformosa.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Formosa",
    },

    # La Rioja
    {
        "name": "La Rioja Digital",
        "rss": "https://www.larioja.com/feed/",
        "url": "https://www.larioja.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "La Rioja",
    },

    # Catamarca
    {
        "name": "El Ancasti",
        "rss": "https://www.elancasti.com.ar/feed/",
        "url": "https://www.elancasti.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Catamarca",
    },

    # San Juan
    {
        "name": "Diario de Cuyo",
        "rss": "https://www.diariodecuyo.com.ar/feed/",
        "url": "https://www.diariodecuyo.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "San Juan",
    },

    # San Luis
    {
        "name": "El Diario de la República",
        "rss": "https://www.eldiariodelarepublica.com/feed/",
        "url": "https://www.eldiariodelarepublica.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "San Luis",
    },

    # Neuquén
    {
        "name": "La Mañana Neuquén",
        "rss": "https://www.lmneuquen.com/feed/",
        "url": "https://www.lmneuquen.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Neuquén",
    },

    # Río Negro
    {
        "name": "Río Negro Online",
        "rss": "https://www.rionegro.com.ar/feed/",
        "url": "https://www.rionegro.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Río Negro",
    },

    # Chubut
    {
        "name": "El Patagónico",
        "rss": "https://www.elpatagonico.com/feed/",
        "url": "https://www.elpatagonico.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Chubut",
    },

    # Santa Cruz
    {
        "name": "La Opinión Austral",
        "rss": "https://www.laopinionaustral.com.ar/feed/",
        "url": "https://www.laopinionaustral.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Santa Cruz",
    },

    # Tierra del Fuego
    {
        "name": "Diario del Fin del Mundo",
        "rss": "https://www.eldiariodelfindelmundo.com/feed/",
        "url": "https://www.eldiariodelfindelmundo.com",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "Tierra del Fuego",
    },

    # La Pampa
    {
        "name": "La Arena",
        "rss": "https://www.laarena.com.ar/feed/",
        "url": "https://www.laarena.com.ar",
        "scrape_links": False,
        "max_articles": 3,
        "provincia": "La Pampa",
    },
]
