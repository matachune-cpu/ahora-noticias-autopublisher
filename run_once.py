"""
Ejecuta UN ciclo completo y sale.
Usado por GitHub Actions — no corre en loop.
"""
import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

from main import run_cycle
import database

database.init_db()
run_cycle()
