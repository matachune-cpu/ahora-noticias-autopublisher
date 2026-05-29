import os
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

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
    # ── PRIORIDAD ALTA ──────────────────────────────────────────────
    {
        "name": "Infobae",
        "rss": "https://www.infobae.com/arc/outboundfeeds/rss/",
        "url": "https://www.infobae.com",
        "scrape_links": False,
        "max_articles": 8,
    },
    # ── SANTIAGO DEL ESTERO — siempre incluido ───────────────────────
    {
        "name": "El Liberal",
        "rss": None,
        "url": "https://www.elliberal.com.ar",
        "scrape_links": True,
        "article_selector": "a[href*='/nota/']",
        "max_articles": 5,
        "always_include": True,
    },
    # ── COMPLEMENTARIO ──────────────────────────────────────────────
    {
        "name": "Cadena 3",
        "rss": None,
        "url": "https://www.cadena3.com",
        "scrape_links": True,
        "article_selector": "a[href*='/noticia/']",
        "max_articles": 4,
    },
]
