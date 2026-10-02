import logging
from logging.handlers import RotatingFileHandler

from src.app.paths import AppPaths


def setup_logging(paths: AppPaths | None = None) -> None:
    paths = paths or AppPaths.for_runtime()
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        handlers=[RotatingFileHandler(paths.log_path, maxBytes=2_000_000, backupCount=3, encoding="utf-8")],
        force=True,
    )
