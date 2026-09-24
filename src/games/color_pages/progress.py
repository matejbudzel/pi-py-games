"""Small atomic on-disk progress store for external coloring pages."""
from __future__ import annotations

import json
from pathlib import Path


class ProgressStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.records: dict[str, dict] = {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            self.records = data.get("pages", {}) if isinstance(data, dict) else {}
        except (OSError, ValueError):
            pass

    def get(self, source: Path, signature: str) -> dict | None:
        record = self.records.get(str(source.resolve()))
        return record if isinstance(record, dict) and record.get("signature") == signature else None

    def save(self, source: Path, signature: str, colored: set[tuple[int, int]], cursor: list[int], seconds: int, steps: int, completed: bool) -> None:
        self.records[str(source.resolve())] = {
            "signature": signature,
            "colored": sorted([x, y] for x, y in colored),
            "cursor": [int(cursor[0]), int(cursor[1])],
            "seconds": max(0, int(seconds)),
            "steps": max(0, int(steps)),
            "completed": bool(completed),
        }
        try:
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps({"version": 1, "pages": self.records}, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass
