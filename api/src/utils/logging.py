from loguru import logger
import sys

from ..settings import LOG_LEVEL

logger.remove()
# diagnose/backtrace default to True and print every local on each frame of a
# traceback. The house style wraps DB helpers in logger.exception, and
# SQLAlchemy's connect frame holds the psycopg2 params dict — so the first
# connect-time failure would write the Neon password to Cloud Logging.
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="bl | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    diagnose=False,
    backtrace=False,
)
