"""
Tests del circuit breaker y sistema de cuota diaria de Gemini.

Cubre:
- Cuota fresca permite llamada
- Cuota agotada bloquea llamada
- Cooldown activo bloquea llamada
- El contador se incrementa con cada llamada registrada
- rewrite_article devuelve quota_exhausted=True cuando la cuota está agotada
- Los artículos bloqueados por cuota NO se marcan como vistos en main.py
- El reset diario renueva el contador al cambiar la fecha
"""
import json
import os
import time
import tempfile
import unittest
from unittest.mock import patch, MagicMock


class TestCircuitBreakerUnit(unittest.TestCase):
    """Tests unitarios del módulo de cuota — operan sobre un archivo temporal."""

    def setUp(self):
        self.tmp = tempfile.NamedTemporaryFile(
            suffix=".json", delete=False, mode="w"
        )
        self.tmp.close()
        self.quota_file = self.tmp.name

        import rewriter
        self._orig_quota_file = rewriter._QUOTA_FILE
        rewriter._QUOTA_FILE = self.quota_file

    def tearDown(self):
        import rewriter
        rewriter._QUOTA_FILE = self._orig_quota_file
        try:
            os.unlink(self.quota_file)
        except FileNotFoundError:
            pass  # el test lo borró intencionalmente (test_fresh_quota_allows_call)

    # ── helpers ──────────────────────────────────────────────────────────────

    def _write_quota(self, data):
        with open(self.quota_file, "w") as f:
            json.dump(data, f)

    def _read_quota(self):
        with open(self.quota_file) as f:
            return json.load(f)

    # ── tests ─────────────────────────────────────────────────────────────────

    def test_fresh_quota_allows_call(self):
        """Sin archivo de cuota, la primera llamada debe estar permitida."""
        os.unlink(self.quota_file)  # simula workspace limpio
        from rewriter import _can_call_gemini
        can_call, reason = _can_call_gemini()
        self.assertTrue(can_call, f"Debería poder llamar: {reason}")

    def test_exhausted_quota_blocks_call(self):
        """Con el contador al límite, _can_call_gemini devuelve False."""
        from rewriter import _can_call_gemini, _daily_limit
        today = __import__("rewriter")._today_utc()
        self._write_quota({"date": today, "count": _daily_limit(), "cooldown_until": None})

        can_call, reason = _can_call_gemini()
        self.assertFalse(can_call)
        self.assertIn("agotada", reason.lower())

    def test_cooldown_blocks_call(self):
        """Con cooldown activo (unix timestamp en el futuro), bloquea la llamada."""
        from rewriter import _can_call_gemini
        today = __import__("rewriter")._today_utc()
        self._write_quota({
            "date": today,
            "count": 1,
            "cooldown_until": time.time() + 3600,  # 1 hora en el futuro
        })

        can_call, reason = _can_call_gemini()
        self.assertFalse(can_call)
        self.assertIn("cooldown", reason.lower())

    def test_expired_cooldown_allows_call(self):
        """Un cooldown ya vencido no debe bloquear la llamada."""
        from rewriter import _can_call_gemini
        today = __import__("rewriter")._today_utc()
        self._write_quota({
            "date": today,
            "count": 1,
            "cooldown_until": time.time() - 1,  # ya venció
        })

        can_call, _ = _can_call_gemini()
        self.assertTrue(can_call)

    def test_record_call_increments_counter(self):
        """_record_gemini_call incrementa el contador persistido."""
        from rewriter import _record_gemini_call
        today = __import__("rewriter")._today_utc()
        self._write_quota({"date": today, "count": 3, "cooldown_until": None})

        _record_gemini_call()

        data = self._read_quota()
        self.assertEqual(data["count"], 4)

    def test_daily_reset_on_new_date(self):
        """Si el archivo tiene fecha de ayer, el contador vuelve a 0 hoy."""
        from rewriter import _can_call_gemini
        self._write_quota({"date": "2000-01-01", "count": 999, "cooldown_until": None})

        can_call, _ = _can_call_gemini()
        self.assertTrue(can_call)

    def test_rewrite_returns_quota_exhausted_flag(self):
        """Cuando la cuota está agotada, rewrite_article devuelve quota_exhausted=True."""
        from rewriter import rewrite_article, _daily_limit
        today = __import__("rewriter")._today_utc()
        self._write_quota({"date": today, "count": _daily_limit(), "cooldown_until": None})

        result = rewrite_article("Título de prueba", "Texto de prueba.", "Fuente")
        self.assertFalse(result.get("es_publicable"))
        self.assertTrue(result.get("quota_exhausted"), "Debe incluir quota_exhausted=True")

    def test_genuine_rejection_has_no_quota_exhausted(self):
        """Un rechazo real de Gemini (es_publicable=False) NO lleva quota_exhausted."""
        import rewriter

        fake_response = MagicMock()
        fake_response.text = json.dumps({"es_publicable": False})

        fake_client = MagicMock()
        fake_client.models.generate_content.return_value = fake_response

        today = rewriter._today_utc()
        self._write_quota({"date": today, "count": 0, "cooldown_until": None})

        with patch.object(rewriter, "_get_client", return_value=fake_client):
            result = rewriter.rewrite_article("Título", "Texto corto.", "Fuente")

        self.assertFalse(result.get("es_publicable"))
        self.assertFalse(result.get("quota_exhausted", False))


class TestMainQuotaHandling(unittest.TestCase):
    """Verifica que main.py NO llame mark_seen cuando la cuota está agotada."""

    def test_quota_exhausted_skips_mark_seen(self):
        """
        Cuando rewrite_article devuelve quota_exhausted=True,
        process_source no debe llamar database.mark_seen().
        """
        import main
        import database

        quota_result = {
            "es_publicable": False,
            "quota_exhausted": True,
            "title": "",
            "body_html": "",
            "instagram_caption": "",
            "whatsapp_text": "",
            "categoria": "",
            "region": "Argentina",
            "ig_relevancia": 1,
        }

        fake_entry = {
            "url": "https://ejemplo.com/articulo-test",
            "title": "Artículo de prueba",
            "summary": "Resumen",
            "image_url": None,
            "full_text": None,
        }
        fake_article = MagicMock()
        fake_article.title = "Artículo de prueba"
        fake_article.full_text = "Contenido del artículo."
        fake_article.image_url = None

        source = {"name": "Fuente Test", "url": "https://ejemplo.com/rss"}

        with patch("main.fetch_entries", return_value=[fake_entry]), \
             patch("main.database.is_published", return_value=False), \
             patch("main._es_irrelevante", return_value=False), \
             patch("main.es_tema_duplicado", return_value=(False, "", 0.0)), \
             patch("main.extract_article", return_value=fake_article), \
             patch("main.rewrite_article", return_value=quota_result), \
             patch("main.database.mark_seen") as mock_mark_seen:

            main.process_source(source, [], [0])

        mock_mark_seen.assert_not_called()

    def test_real_rejection_calls_mark_seen(self):
        """
        Cuando Gemini rechaza genuinamente (es_publicable=False, sin quota_exhausted),
        process_source SÍ llama database.mark_seen().
        """
        import main

        reject_result = {
            "es_publicable": False,
            "quota_exhausted": False,
            "title": "",
            "body_html": "",
            "instagram_caption": "",
            "whatsapp_text": "",
            "categoria": "",
            "region": "Argentina",
            "ig_relevancia": 1,
        }

        fake_entry = {
            "url": "https://ejemplo.com/articulo-irrelevante",
            "title": "Sorteo de lotería",
            "summary": "Resumen",
            "image_url": None,
            "full_text": None,
        }
        fake_article = MagicMock()
        fake_article.title = "Sorteo de lotería"
        fake_article.full_text = "Números ganadores."
        fake_article.image_url = None

        source = {"name": "Fuente Test", "url": "https://ejemplo.com/rss"}

        with patch("main.fetch_entries", return_value=[fake_entry]), \
             patch("main.database.is_published", return_value=False), \
             patch("main._es_irrelevante", return_value=False), \
             patch("main.es_tema_duplicado", return_value=(False, "", 0.0)), \
             patch("main.extract_article", return_value=fake_article), \
             patch("main.rewrite_article", return_value=reject_result), \
             patch("main.database.mark_seen") as mock_mark_seen:

            main.process_source(source, [], [0])

        mock_mark_seen.assert_called_once()


if __name__ == "__main__":
    unittest.main()
