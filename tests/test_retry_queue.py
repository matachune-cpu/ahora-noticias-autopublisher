"""
Tests de la cola de reintentos (retry_queue).

Escenarios críticos:
- Una noticia guardada por cuota agotada puede recuperarse aunque desaparezca del RSS
- Deduplicación funciona en reintentos
- Artículos ya publicados se limpian de la cola automáticamente
- Cuota agotada pausa el proceso sin perder artículos
- Un fallo de WordPress mantiene el artículo en la cola
"""
import os
import json
import tempfile
import sqlite3
import unittest
from unittest.mock import patch, MagicMock, call


class TestRetryQueueDatabase(unittest.TestCase):
    """Tests de las funciones de base de datos de retry_queue."""

    def setUp(self):
        import database
        self._orig_db = database.DB_PATH
        self._tmp_db = tempfile.mktemp(suffix=".db")
        database.DB_PATH = self._tmp_db
        database.init_db()

    def tearDown(self):
        import database
        database.DB_PATH = self._orig_db
        try:
            os.unlink(self._tmp_db)
        except FileNotFoundError:
            pass

    def test_add_and_retrieve_pending(self):
        """Un artículo guardado en la cola aparece en get_pending."""
        import database
        url = "https://ejemplo.com/noticia-1"
        database.retry_queue_add(
            url=url, title="Título de prueba",
            full_text="Texto completo de prueba.", source="Fuente Test",
        )
        pending = database.retry_queue_get_pending()
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["url"], url)
        self.assertEqual(pending[0]["title"], "Título de prueba")

    def test_add_idempotent(self):
        """Agregar la misma URL dos veces no crea duplicados."""
        import database
        url = "https://ejemplo.com/noticia-dup"
        database.retry_queue_add(url=url, title="T", full_text="F", source="S")
        database.retry_queue_add(url=url, title="T", full_text="F", source="S")
        self.assertEqual(database.retry_queue_count_pending(), 1)

    def test_mark_done_removes_from_pending(self):
        """Marcar como done elimina el artículo de los pendientes."""
        import database
        url = "https://ejemplo.com/noticia-done"
        database.retry_queue_add(url=url, title="T", full_text="F", source="S")
        database.retry_queue_mark_done(url)
        self.assertEqual(database.retry_queue_count_pending(), 0)

    def test_mark_discarded_removes_from_pending(self):
        """Marcar como descartado elimina el artículo de los pendientes."""
        import database
        url = "https://ejemplo.com/noticia-disc"
        database.retry_queue_add(url=url, title="T", full_text="F", source="S")
        database.retry_queue_mark_discarded(url)
        self.assertEqual(database.retry_queue_count_pending(), 0)

    def test_priority_order(self):
        """Los artículos de mayor prioridad se devuelven primero."""
        import database
        database.retry_queue_add(url="https://a.com/1", title="T1", full_text="F", source="S", priority=3)
        database.retry_queue_add(url="https://a.com/2", title="T2", full_text="F", source="S", priority=9)
        database.retry_queue_add(url="https://a.com/3", title="T3", full_text="F", source="S", priority=5)
        pending = database.retry_queue_get_pending(limit=3)
        priorities = [p["priority"] for p in pending]
        self.assertEqual(priorities, sorted(priorities, reverse=True))

    def test_image_url_persisted(self):
        """La URL de imagen se guarda y se recupera correctamente."""
        import database
        img = "https://cdn.ejemplo.com/foto.jpg"
        database.retry_queue_add(
            url="https://ejemplo.com/foto", title="T", full_text="F",
            source="S", image_url=img,
        )
        pending = database.retry_queue_get_pending()
        self.assertEqual(pending[0]["image_url"], img)

    def test_cleanup_removes_published(self):
        """cleanup_published marca como done artículos que ya fueron publicados."""
        import database
        url = "https://ejemplo.com/ya-publicado"
        database.retry_queue_add(url=url, title="T", full_text="F", source="S")
        # Simular publicación por otro camino (urgent.yml)
        database.mark_published(url=url, title="T", source="S", wp_post_id="123")
        # cleanup debe detectarlo
        database.retry_queue_cleanup_published()
        self.assertEqual(database.retry_queue_count_pending(), 0)


class TestRetryQueueRecovery(unittest.TestCase):
    """
    Escenario crítico: noticia recuperada aunque desapareció del RSS.
    Demuestra que el ciclo la procesa desde la cola aunque no esté en el feed.
    """

    def setUp(self):
        import database, rewriter
        # DB temporal
        self._orig_db = database.DB_PATH
        self._tmp_db = tempfile.mktemp(suffix=".db")
        database.DB_PATH = self._tmp_db
        database.init_db()
        # Quota temporal
        self._orig_quota = rewriter._QUOTA_FILE
        self._tmp_quota = tempfile.mktemp(suffix=".json")
        rewriter._QUOTA_FILE = self._tmp_quota

    def tearDown(self):
        import database, rewriter
        database.DB_PATH = self._orig_db
        rewriter._QUOTA_FILE = self._orig_quota
        for f in [self._tmp_db, self._tmp_quota]:
            try:
                os.unlink(f)
            except FileNotFoundError:
                pass

    def test_article_saved_on_quota_exhaustion(self):
        """
        Cuando la cuota está agotada, process_source guarda el artículo en retry_queue.
        """
        import database, rewriter, main

        # Cuota agotada
        today = rewriter._today_utc()
        with open(self._tmp_quota, "w") as f:
            json.dump({"date": today, "count": 18, "cooldown_until": None}, f)

        quota_result = {**rewriter._RESULTADO_NO_PUBLICABLE, "quota_exhausted": True}

        fake_entry = {
            "url": "https://ejemplo.com/noticia-cuota",
            "title": "Noticia importante bloqueada por cuota",
            "summary": "", "image_url": None, "full_text": None,
        }
        fake_article = MagicMock()
        fake_article.title = "Noticia importante bloqueada por cuota"
        fake_article.full_text = "Texto completo de la noticia importante."
        fake_article.image_url = None

        source = {"name": "Fuente Test", "url": "https://ejemplo.com/rss"}

        with patch("main.fetch_entries", return_value=[fake_entry]), \
             patch("main.database.is_published", return_value=False), \
             patch("main._es_irrelevante", return_value=False), \
             patch("main.es_tema_duplicado", return_value=(False, "", 0.0)), \
             patch("main.extract_article", return_value=fake_article), \
             patch("main.rewrite_article", return_value=quota_result):

            main.process_source(source, [], [0])

        # El artículo DEBE estar en la cola de reintentos
        pending = database.retry_queue_get_pending()
        self.assertEqual(len(pending), 1, "El artículo debe estar en retry_queue")
        self.assertEqual(pending[0]["url"], "https://ejemplo.com/noticia-cuota")
        self.assertEqual(pending[0]["full_text"], "Texto completo de la noticia importante.")

    def test_article_processed_from_queue_even_without_rss(self):
        """
        Un artículo en retry_queue se procesa en run_cycle aunque el RSS esté vacío.
        Esto simula que la noticia desapareció del feed.
        """
        import database, rewriter, main

        # Guardar artículo en cola (simula ciclo anterior con cuota agotada)
        url = "https://ejemplo.com/noticia-sin-rss"
        database.retry_queue_add(
            url=url,
            title="Noticia que ya no está en el RSS",
            full_text="Texto completo preservado en la cola de reintentos.",
            source="Fuente Test",
            priority=8,
        )

        # Cuota disponible ahora (nuevo día o cooldown expirado)
        today = rewriter._today_utc()
        with open(self._tmp_quota, "w") as f:
            json.dump({"date": today, "count": 0, "cooldown_until": None}, f)

        # Gemini reescribe exitosamente
        rewrite_ok = {
            "es_publicable": True,
            "title": "Noticia reescrita exitosamente",
            "body_html": "<p>" + "Contenido " * 60 + "</p>",
            "instagram_caption": "Caption IG",
            "facebook_caption": "Caption FB",
            "whatsapp_text": "Texto WA",
            "categoria": "Política",
            "region": "Argentina",
            "ig_relevancia": 8,
            "es_catastrofe": False,
        }

        with patch("main.rewrite_article", return_value=rewrite_ok), \
             patch("main._publish_pipeline", return_value=True) as mock_publish:

            main.process_retry_queue([], [0])

        # El pipeline de publicación debe haberse llamado
        mock_publish.assert_called_once()
        args = mock_publish.call_args
        self.assertEqual(args.kwargs["url"] if args.kwargs else args[1].get("url") or args[0][0], url)

        # El artículo debe estar marcado como done en la cola
        self.assertEqual(database.retry_queue_count_pending(), 0)

    def test_quota_still_exhausted_pauses_without_losing(self):
        """
        Si la cuota sigue agotada en el reintento, el artículo NO se pierde — queda pending.
        """
        import database, rewriter, main

        url = "https://ejemplo.com/noticia-cuota-2"
        database.retry_queue_add(
            url=url, title="Noticia pendiente", full_text="Texto.", source="S",
        )

        # Cuota sigue agotada
        today = rewriter._today_utc()
        with open(self._tmp_quota, "w") as f:
            json.dump({"date": today, "count": 18, "cooldown_until": None}, f)

        main.process_retry_queue([], [0])

        # Artículo DEBE seguir en la cola (no fue descartado)
        self.assertEqual(database.retry_queue_count_pending(), 1)

    def test_wordpress_failure_keeps_article_in_queue(self):
        """
        Si WordPress falla durante el reintento, el artículo permanece en cola
        para el próximo ciclo.
        """
        import database, rewriter, main

        url = "https://ejemplo.com/noticia-wp-fail"
        database.retry_queue_add(
            url=url, title="Noticia WP fallida", full_text="Texto.", source="S",
        )

        today = rewriter._today_utc()
        with open(self._tmp_quota, "w") as f:
            json.dump({"date": today, "count": 0, "cooldown_until": None}, f)

        rewrite_ok = {
            "es_publicable": True, "title": "Reescrito",
            "body_html": "<p>" + "x" * 300 + "</p>",
            "instagram_caption": "", "facebook_caption": "", "whatsapp_text": "",
            "categoria": "Política", "region": "Argentina", "ig_relevancia": 7, "es_catastrofe": False,
        }

        with patch("main.rewrite_article", return_value=rewrite_ok), \
             patch("main._publish_pipeline", return_value=False):  # WP falló

            main.process_retry_queue([], [0])

        # Artículo debe seguir en la cola — pipeline devolvió False
        self.assertEqual(database.retry_queue_count_pending(), 1)

    def test_duplicate_in_retry_discarded_not_published(self):
        """
        Si el tema del artículo en cola ya fue cubierto, se descarta sin publicar.
        """
        import database, rewriter, main

        url = "https://ejemplo.com/noticia-dup-retry"
        database.retry_queue_add(
            url=url, title="Presidente anuncia nueva medida económica",
            full_text="Texto.", source="S",
        )

        today = rewriter._today_utc()
        with open(self._tmp_quota, "w") as f:
            json.dump({"date": today, "count": 0, "cooldown_until": None}, f)

        # Simular que el tema ya fue cubierto
        titulos_recientes = ["Gobierno anuncia paquete económico histórico"]

        with patch("main._publish_pipeline") as mock_publish:
            main.process_retry_queue(titulos_recientes, [0])

        # No debe haber publicado nada
        mock_publish.assert_not_called()
        # Artículo marcado como descartado
        self.assertEqual(database.retry_queue_count_pending(), 0)


if __name__ == "__main__":
    unittest.main()
