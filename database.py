import sqlite3
import hashlib
from datetime import datetime, date

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
        # Cola de publicación para Instagram: artículos relevantes esperando su ventana horaria
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ig_queue (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                url_hash TEXT UNIQUE NOT NULL,
                original_url TEXT NOT NULL,
                title TEXT,
                ig_caption TEXT,
                flyer_public_url TEXT,
                relevance_score INTEGER DEFAULT 0,
                queued_at TEXT DEFAULT CURRENT_TIMESTAMP,
                posted_at TEXT,
                ig_post_id TEXT
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


# ── Cola de Instagram ─────────────────────────────────────────────────────────

def ig_queue_add(
    url: str,
    title: str,
    ig_caption: str,
    flyer_public_url: str,
    relevance_score: int,
) -> bool:
    """
    Agrega un artículo a la cola de Instagram.
    Retorna True si se insertó, False si ya estaba.
    """
    try:
        with sqlite3.connect(DB_PATH) as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO ig_queue
                    (url_hash, original_url, title, ig_caption, flyer_public_url, relevance_score)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (url_hash(url), url, title, ig_caption, flyer_public_url, relevance_score),
            )
            conn.commit()
            return conn.total_changes > 0
    except Exception:
        return False


def ig_queue_get_pending(limit: int = 3) -> list[dict]:
    """
    Devuelve los próximos artículos pendientes de publicar en Instagram,
    ordenados por relevancia (mayor primero) y luego por fecha de cola (FIFO).
    Solo los que no tienen posted_at.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """
            SELECT * FROM ig_queue
            WHERE posted_at IS NULL AND flyer_public_url IS NOT NULL
            ORDER BY relevance_score DESC, queued_at ASC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def ig_queue_mark_posted(url: str, ig_post_id: str):
    """Marca un artículo de la cola como publicado en Instagram."""
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE ig_queue
            SET posted_at = ?, ig_post_id = ?
            WHERE url_hash = ?
            """,
            (datetime.utcnow().isoformat(), ig_post_id, url_hash(url)),
        )
        # También actualizar la tabla principal de artículos con el ig_post_id
        conn.execute(
            "UPDATE articles SET ig_post_id = ? WHERE url_hash = ?",
            (ig_post_id, url_hash(url)),
        )
        conn.commit()


def ig_queue_count_today() -> int:
    """Cuántos posts de IG se publicaron hoy (desde ig_queue)."""
    try:
        with sqlite3.connect(DB_PATH) as conn:
            today = date.today().isoformat()
            row = conn.execute(
                "SELECT COUNT(*) FROM ig_queue WHERE posted_at LIKE ? AND ig_post_id IS NOT NULL",
                (f"{today}%",),
            ).fetchone()
            return row[0] if row else 0
    except Exception:
        return 0


def get_recent_titles(hours: int = 12) -> list[str]:
    """
    Retorna los títulos de artículos publicados en las últimas N horas.
    Usado para detectar notas sobre el mismo tema de distintas fuentes.
    """
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(hours=hours)).isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute(
            "SELECT title FROM articles WHERE published_at > ? AND title IS NOT NULL",
            (cutoff,),
        ).fetchall()
        return [r[0] for r in rows]


def mark_seen(url: str, title: str, source: str):
    """
    Registra una URL como 'vista' (sin publicar) para no reprocesarla.
    Se usa cuando se detecta que es un tema ya cubierto por otra fuente.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO articles
                (url_hash, original_url, title, source, published_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (url_hash(url), url, title, source, datetime.utcnow().isoformat()),
        )
        conn.commit()


def ig_queue_count_pending() -> int:
    """Cuántos artículos esperan en la cola."""
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute(
            "SELECT COUNT(*) FROM ig_queue WHERE posted_at IS NULL"
        ).fetchone()
        return row[0] if row else 0
