from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from cloakbrowser import launch_async

from .client import BlockedError, FetchError, NotFoundError, fetch_json

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


@dataclass
class FetchConfig:
    url_template: str
    parse: Callable[[dict], dict]
    required_fields: tuple[str, ...]
    output_dir: Path
    logs_dir: Path
    batch_size: int = 1000
    concurrency: int = 3
    retries: int = 3
    backoff_base: float = 2.0
    proxy: str | None = None


@dataclass
class PipelineStats:
    batches_total: int = 0
    batches_skipped: int = 0
    fetched: int = 0
    not_found: int = 0
    failed: int = 0
    blocked: int = 0


async def _fetch_one(pool, raw_id, config, records, not_found, failed, blocked) -> None:
    url = config.url_template.format(id=raw_id)
    page = await pool.get()
    try:
        raw = await fetch_json(page, url, config.retries, config.backoff_base)
    except NotFoundError:
        not_found.append(raw_id)
        return
    except BlockedError as exc:
        logger.error("blocked (WAF signature) for id=%s: %s", raw_id, exc)
        failed.append(raw_id)
        blocked.append(raw_id)
        return
    except FetchError as exc:
        logger.error("giving up on id=%s: %s", raw_id, exc)
        failed.append(raw_id)
        return
    except Exception as exc:
        # A malformed response (e.g. a 200 with a non-JSON body) raises
        # something other than NotFoundError/FetchError. One bad id must
        # not crash the whole batch (and, uncaught, the whole 600k-id run).
        logger.exception("unexpected error fetching id=%s: %s", raw_id, exc)
        failed.append(raw_id)
        return
    finally:
        # Return the page to the pool so another id can reuse it (keeping its
        # solved-challenge cookie). Concurrency is bounded by the pool size.
        pool.put_nowait(page)

    try:
        record = config.parse(raw)
        if not validate_record(record, int(raw_id), config.required_fields):
            logger.warning("validation failed for id=%s", raw_id)
            failed.append(raw_id)
            return
    except Exception:
        logger.exception("parse/validate failed for id=%s", raw_id)
        failed.append(raw_id)
        return

    records.append(record)


async def fetch_batch(pool, ids_batch: list[str], config: FetchConfig):
    records: list[dict] = []
    not_found: list[str] = []
    failed: list[str] = []
    blocked: list[str] = []
    await asyncio.gather(
        *(
            _fetch_one(pool, raw_id, config, records, not_found, failed, blocked)
            for raw_id in ids_batch
        )
    )

    deduped: dict[int, dict] = {}
    for record in records:
        if record["id"] in deduped:
            logger.warning("duplicate id %s within batch, keeping first", record["id"])
            continue
        deduped[record["id"]] = record
    return list(deduped.values()), not_found, failed, blocked


def _append_lines(path: Path, lines: list[str]) -> None:
    if not lines:
        return
    # Write an "id" header on first creation so the log file is itself a
    # valid --input CSV (ids.load_ids requires an "id" column header) —
    # not_found/failed ids can be re-run standalone without manual editing.
    is_new = not path.exists()
    with path.open("a", encoding="utf-8") as f:
        if is_new:
            f.write("id\n")
        for line in lines:
            f.write(line + "\n")


async def run_pipeline(ids: list[str], config: FetchConfig) -> PipelineStats:
    config.output_dir.mkdir(parents=True, exist_ok=True)
    config.logs_dir.mkdir(parents=True, exist_ok=True)

    ranges = batch_ranges(len(ids), config.batch_size)
    stats = PipelineStats(batches_total=len(ranges))
    # Each concurrency unit is a live Chromium tab (~50-80MB), not a cheap
    # socket — so the pool is a FIXED `concurrency` pages, sized up front.
    # Pages are reused across ids so each keeps the anti-bot cookie it earned
    # solving Tiki's JS WAF challenge.
    n_pages = max(1, config.concurrency)

    browser = await launch_async(proxy=config.proxy)
    try:
        pool: asyncio.Queue = asyncio.Queue()
        for _ in range(n_pages):
            pool.put_nowait(await browser.new_page())

        for start, end in ranges:
            out_path = config.output_dir / output_filename(start, end)
            if batch_is_done(out_path):
                stats.batches_skipped += 1
                continue

            batch_slice = ids[start : end + 1]
            records, not_found, failed, blocked = await fetch_batch(pool, batch_slice, config)

            # Log not_found/failed ids BEFORE writing the batch file: the
            # batch file's existence is the resume marker (batch_is_done), so
            # if a crash lands between these two writes, we want the batch to
            # be re-fetched on resume (at worst duplicate log lines) rather
            # than have batch_is_done mark it "done" while its failure/
            # not-found ids were never logged and never will be.
            _append_lines(config.logs_dir / "not_found_ids.txt", not_found)
            _append_lines(config.logs_dir / "failed_ids.txt", failed)
            write_batch_atomic(out_path, records)

            stats.fetched += len(records)
            stats.not_found += len(not_found)
            stats.failed += len(failed)
            stats.blocked += len(blocked)

            if blocked:
                logger.warning("batch %d-%d: WAF block signature on %d ids", start, end, len(blocked))
            logger.info(
                "batch %d-%d: %d ok, %d not_found, %d failed (%d blocked) at concurrency=%d",
                start, end, len(records), len(not_found), len(failed), len(blocked), n_pages,
            )
    finally:
        await browser.close()

    return stats
