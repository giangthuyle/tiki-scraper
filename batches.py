from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from tiki_scraper.ids import load_ids

BATCH_SIZE = int(os.environ.get("BATCH_SIZE", "50"))
_DATA_DIR = Path(__file__).resolve().parent / "data"


def batch_bounds(batch_id: int, total: int, batch_size: int) -> tuple[int, int]:
    if batch_id < 0:
        raise IndexError(f"batch_id {batch_id} < 0")
    start = batch_id * batch_size
    if start >= total:
        raise IndexError(f"batch_id {batch_id} out of range (total={total})")
    end = min(start + batch_size, total) - 1
    return start, end


@lru_cache(maxsize=1)
def all_ids() -> tuple[str, ...]:
    paths = sorted(_DATA_DIR.glob("products-*.csv"))
    ids, _ = load_ids(paths)
    return tuple(ids)


def batch_slice(batch_id: int) -> tuple[int, int, list[str]]:
    ids = all_ids()
    start, end = batch_bounds(batch_id, len(ids), BATCH_SIZE)
    return start, end, list(ids[start : end + 1])


def parse_batch_id(body: dict | None, params: dict) -> int:
    raw = None
    if isinstance(body, dict) and "batch_id" in body:
        raw = body["batch_id"]
    elif params.get("batch_id") is not None:
        raw = params.get("batch_id")
    if raw is None:
        raise ValueError("missing batch_id")
    try:
        return int(raw)
    except (TypeError, ValueError):
        raise ValueError(f"batch_id not an integer: {raw!r}")
