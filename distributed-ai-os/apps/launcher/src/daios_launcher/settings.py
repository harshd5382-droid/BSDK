"""Persistent launcher settings."""

from __future__ import annotations

import json
import secrets
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, Field

SETTINGS_PATH = Path.home() / ".daios" / "launcher.json"


class LauncherSettings(BaseModel):
    role: Literal["coordinator", "worker"] = "coordinator"
    cluster_token: str | None = Field(default=None)
    install_dir: str | None = None
    autostart_node: bool = False
    launcher_port: int = 8090
    active_model: str | None = None

    @classmethod
    def load(cls) -> LauncherSettings:
        if not SETTINGS_PATH.is_file():
            return cls()
        try:
            data = json.loads(SETTINGS_PATH.read_text())
            return cls.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            return cls()

    def save(self) -> None:
        SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        SETTINGS_PATH.write_text(self.model_dump_json(indent=2))

    def ensure_token(self) -> str:
        if not self.cluster_token:
            self.cluster_token = secrets.token_urlsafe(32)
            self.save()
        return self.cluster_token


def get_or_create_token() -> str:
    settings = LauncherSettings.load()
    return settings.ensure_token()
