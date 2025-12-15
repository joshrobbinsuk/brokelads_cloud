from loguru import logger
import sys

from ..settings import LOG_LEVEL

logger.remove()
logger.add(
    sys.stdout,
    level=LOG_LEVEL,
    format="bl | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)
