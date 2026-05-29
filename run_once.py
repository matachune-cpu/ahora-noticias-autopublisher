"""
Ejecuta UN ciclo completo y sale.
Usado por GitHub Actions y ejecución local.
Timeout: 10 min en Linux/Mac (SIGALRM), sin timeout en Windows.
"""
import logging
import sys
import signal
import platform

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("run_once")

# SIGALRM solo existe en Unix
if platform.system() != "Windows":
    def _timeout_handler(signum, frame):
        logger.warning("Tiempo limite alcanzado. Saliendo.")
        sys.exit(0)
    signal.signal(signal.SIGALRM, _timeout_handler)
    signal.alarm(600)

from main import run_cycle
import database

database.init_db()
run_cycle()

if platform.system() != "Windows":
    signal.alarm(0)

logger.info("Ciclo completado correctamente.")
