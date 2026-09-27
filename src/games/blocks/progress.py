"""Best-score persistence, deliberately tiny and tolerant of a missing disk."""
from __future__ import annotations

import json
from pathlib import Path


class HighScoreStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            value = json.loads(path.read_text(encoding="utf-8")).get("high_score", 0)
            self.high_score = value if isinstance(value, int) and value >= 0 else 0
        except (OSError, ValueError, AttributeError):
            self.high_score = 0

    def record(self, score: int) -> bool:
        if score <= self.high_score:
            return False
        self.high_score = score
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps({"version": 1, "high_score": score}, separators=(",", ":")), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass
        return True
