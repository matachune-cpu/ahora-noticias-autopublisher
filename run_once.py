"""
Ejecuta UN ciclo completo y sale.
Usado por GitHub Actions — no corre en loop.
Timeout máximo: 10 minutos.
"""
import logging
import sys
import signal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger("run_once")

def _timeout_handler(signum, frame):
    logger.warning("Tiempo limite alcanzado. Guardando DB y saliendo.")
    sys.exit(0)

# Timeout de 10 minutos (600 segundos)
signal.signal(signal.SIGALRM, _timeout_handler)
signal.alarm(600)

from main import run_cycle
import database

database.init_db()
run_cycle()
signal.alarm(0)  # cancelar alarma si terminó normalmente
logger.info("Ciclo completado correctamente.")
