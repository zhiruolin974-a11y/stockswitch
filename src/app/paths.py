"""Runtime and writable path policy shared by the desktop application."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_HOME_OVERRIDE = "STOCKSWITCH_DATA_HOME"


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def resource_path(name: str) -> Path:
    """Locate a bundled read-only asset, never a writable data file."""
    relative = Path(name)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Resource name must be relative to the application bundle")
    bundle_root = Path(getattr(sys, "_MEIPASS", PROJECT_ROOT)) if is_frozen() else PROJECT_ROOT
    return bundle_root / relative


@dataclass(frozen=True)
class AppPaths:
    app_data_dir: Path

    @classmethod
    def for_runtime(cls, *, frozen: bool | None = None,
                    environ: Mapping[str, str] | None = None) -> AppPaths:
        environment = os.environ if environ is None else environ
        override = environment.get(DATA_HOME_OVERRIDE)
        if override:
            return cls(Path(override).expanduser().resolve())
        frozen = is_frozen() if frozen is None else frozen
        if not frozen:
            return cls(PROJECT_ROOT)
        local = environment.get("LOCALAPPDATA")
        if not local:
            raise RuntimeError("LOCALAPPDATA is required for a packaged Windows installation")
        return cls(Path(local).resolve() / "StockSwitch")

    @property
    def config_dir(self) -> Path:
        return self.app_data_dir / "config"

    @property
    def config_path(self) -> Path:
        return self.config_dir / "config.toml"

    @property
    def data_dir(self) -> Path:
        return self.app_data_dir / "data"

    @property
    def history_dir(self) -> Path:
        return self.data_dir / "history"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "stockswitch.db"

    @property
    def backtests_path(self) -> Path:
        return self.data_dir / "backtests.db"

    @property
    def history_database_path(self) -> Path:
        return self.history_dir / "daily.sqlite"

    @property
    def logs_dir(self) -> Path:
        return self.app_data_dir / "logs"

    @property
    def exports_dir(self) -> Path:
        return self.app_data_dir / "exports"

    @property
    def cache_dir(self) -> Path:
        return self.app_data_dir / "cache"

    @property
    def log_path(self) -> Path:
        return self.logs_dir / "stockswitch.log"

    def initialize(self) -> None:
        for directory in (self.app_data_dir, self.config_dir, self.data_dir,
                          self.history_dir, self.logs_dir, self.exports_dir, self.cache_dir):
            directory.mkdir(parents=True, exist_ok=True)
        # Development mode retains its existing root-level config.toml convention.
        destination = self.app_data_dir / "config.toml" if self.app_data_dir == PROJECT_ROOT else self.config_path
        if not destination.exists():
            template = resource_path("config.example.toml").read_bytes()
            try:
                with destination.open("xb") as handle:
                    handle.write(template)
            except FileExistsError:
                pass
