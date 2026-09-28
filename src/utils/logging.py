import logging
from logging.handlers import RotatingFileHandler

from src.app.config import ROOT


def setup_logging() -> None:
    directory = ROOT / "logs"
    directory.mkdir(exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[RotatingFileHandler(directory / "stockswitch.log", maxBytes=2_000_000, backupCount=3, encoding="utf-8")],
        force=True,
    )
