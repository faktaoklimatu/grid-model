import logging
import sys

ROOT_LOGGER_NAME = "energy_insights"


def get_logger(name: str | None = None) -> logging.Logger:
    """
    Get a logger instance by name.
    If name is None, return the root logger.
    """
    return logging.getLogger(name)


def set_debug(debug=True) -> None:
    """
    Get a logger instance by name.
    If name is None, return the root logger.
    """
    get_logger(ROOT_LOGGER_NAME).setLevel(logging.DEBUG if debug else logging.INFO)


def setup_logging(level=logging.INFO) -> None:
    logger = logging.getLogger(ROOT_LOGGER_NAME)
    logger.setLevel(level)
    logger.propagate = False

    handler = logging.StreamHandler(sys.stderr)
    date_format = "%Y-%m-%d %H:%M:%S"

    formatter = logging.Formatter(
        fmt="{asctime} [{levelname}] {message}",
        datefmt=date_format,
        style="{",
    )

    handler.setFormatter(formatter)
    logger.addHandler(handler)
