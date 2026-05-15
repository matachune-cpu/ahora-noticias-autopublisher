import sqlite3
import hashlib
from datetime import datetime

DB_PATH = "published_articles.db"


def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS articles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                original_url TEXT NOT NULL,
                title TEXT,
                source TEXT,
                published_at TEXT,
                wp_post_id TEXT,
                fb_post_id TEXT,
                ig_post_id TEXT,
                wa_sent INTEGER DEFAULT 0,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            )
        """)
        conn.commit()


def url_hash(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def is_published(url: str) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT id FROM articles WHERE url_hash = ?", (url_hash(url),)
        ).fetchone()
        return row is not None


def mark_published(
    url: str,
    title: str,
    source: str,
    wp_post_id: str = None,
    fb_post_id: str = None,
    ig_post_id: str = None,
    wa_sent: bool = False,
):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO articles
                (url_hash, original_url, title, source, published_at, wp_post_id, fb_post_id, ig_post_id, wa_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                url_hash(url),
                url,
                title,
                source,
                datetime.utcnow().isoformat(),
                wp_post_id,
                fb_post_id,
                ig_post_id,
                1 if wa_sent else 0,
            ),
        )
        conn.commit()
