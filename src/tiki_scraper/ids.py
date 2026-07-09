from __future__ import annotations

import csv
import re
from pathlib import Path

_ID_RE = re.compile(r"^[1-9]\d*$")


def is_valid_id(raw: str) -> bool:
    return bool(_ID_RE.match(raw.strip()))


def load_ids(paths: list[Path]) -> tuple[list[str], dict[str, int]]:
    seen: set[str] = set()
    ids: list[str] = []
    stats = {"total_read": 0, "invalid": 0, "duplicate": 0, "valid": 0}

    for path in paths:
        with path.open(newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                raw = (row.get("id") or "").strip()
                stats["total_read"] += 1
                if not is_valid_id(raw):
                    stats["invalid"] += 1
                    continue
                if raw in seen:
                    stats["duplicate"] += 1
                    continue
                seen.add(raw)
                ids.append(raw)
                stats["valid"] += 1

    return ids, stats
