import json
import time
from pathlib import Path
from typing import Any


class JsonCache:
    """Small on-disk key/value cache so re-runs don't repeat network/LLM calls."""

    def __init__(self, path: Path, ttl_s: int | None = None):
        self.path = path
        self.ttl_s = ttl_s
        self._data: dict[str, dict[str, Any]] = {}
        if path.exists():
            try:
                self._data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                self._data = {}

    def get(self, key: str) -> Any | None:
        entry = self._data.get(key)
        if entry is None:
            return None
        if self.ttl_s is not None and time.time() - entry["at"] > self.ttl_s:
            return None
        return entry["value"]

    def set(self, key: str, value: Any) -> None:
        self._data[key] = {"at": time.time(), "value": value}

    def save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._data), encoding="utf-8")
        except OSError:
            pass
