from loguru import logger

from config.settings import LOG_FILE


def setup_logging():
    logger.add(LOG_FILE, rotation="100 MB")
    return logger
