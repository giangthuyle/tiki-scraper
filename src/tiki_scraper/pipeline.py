from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def batch_ranges(total: int, batch_size: int) -> list[tuple[int, int]]:
    ranges = []
    start = 0
    while start < total:
        end = min(start + batch_size, total) - 1
        ranges.append((start, end))
        start = end + 1
    return ranges


def output_filename(start: int, end: int) -> str:
    return f"products_{start:07d}-{end:07d}.json"


def write_batch_atomic(path: Path, records: list[dict]) -> None:
    tmp_path = path.with_name(path.name + ".tmp")
    tmp_path.write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def batch_is_done(path: Path) -> bool:
    if not path.exists():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return False
    return isinstance(data, list)


def validate_record(record: dict, requested_id: int, required_fields: tuple[str, ...]) -> bool:
    if record.get("id") != requested_id:
        return False
    for field in required_fields:
        value = record.get(field)
        if value is None:
            return False
        if isinstance(value, str) and not value.strip():
            return False
    return True


def verify_output(output_dir: Path) -> tuple[int, int]:
    seen: set = set()
    duplicates = 0
    total = 0
    for path in sorted(output_dir.glob("products_*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            logger.warning("could not read %s during verification", path)
            continue
        for record in data:
            total += 1
            rid = record.get("id")
            if rid in seen:
                duplicates += 1
                logger.warning("duplicate id %s found in %s", rid, path)
            else:
                seen.add(rid)
    return total, duplicates
