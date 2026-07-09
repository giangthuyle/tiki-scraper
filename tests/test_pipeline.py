import asyncio
import json
from pathlib import Path

import pytest

from tiki_scraper import pipeline as pipeline_module
from tiki_scraper.client import BlockedError, FetchError, NotFoundError
from tiki_scraper.pipeline import (
    FetchConfig,
    batch_is_done,
    batch_ranges,
    fetch_batch,
    output_filename,
    run_pipeline,
    validate_record,
    verify_output,
    write_batch_atomic,
)


def test_batch_ranges_splits_evenly_and_with_remainder():
    assert batch_ranges(10, 3) == [(0, 2), (3, 5), (6, 8), (9, 9)]
    assert batch_ranges(5, 5) == [(0, 4)]
    assert batch_ranges(0, 5) == []


def test_output_filename_zero_pads():
    assert output_filename(0, 999) == "products_0000000-0000999.json"


def test_write_batch_atomic_and_batch_is_done(tmp_path: Path):
    out = tmp_path / "products_0000000-0000001.json"
    assert batch_is_done(out) is False

    write_batch_atomic(out, [{"id": 1}, {"id": 2}])
    assert batch_is_done(out) is True
    assert json.loads(out.read_text(encoding="utf-8")) == [{"id": 1}, {"id": 2}]
    assert not out.with_name(out.name + ".tmp").exists()


def test_batch_is_done_false_for_corrupt_file(tmp_path: Path):
    out = tmp_path / "corrupt.json"
    out.write_text("not json", encoding="utf-8")
    assert batch_is_done(out) is False


def test_validate_record():
    required = ("id", "name", "url_key", "price", "images")
    good = {"id": 1, "name": "n", "url_key": "k", "price": 100, "images": []}
    assert validate_record(good, requested_id=1, required_fields=required) is True

    assert validate_record(good, requested_id=2, required_fields=required) is False

    missing = dict(good, name=None)
    assert validate_record(missing, requested_id=1, required_fields=required) is False

    blank = dict(good, name="   ")
    assert validate_record(blank, requested_id=1, required_fields=required) is False

    empty_images_ok = dict(good, images=[])
    assert validate_record(empty_images_ok, requested_id=1, required_fields=required) is True


def test_verify_output_counts_duplicates_across_files(tmp_path: Path):
    write_batch_atomic(tmp_path / "products_0000000-0000000.json", [{"id": 1}])
    write_batch_atomic(tmp_path / "products_0000001-0000001.json", [{"id": 1}, {"id": 2}])

    total, duplicates = verify_output(tmp_path)

    assert total == 3
    assert duplicates == 1


def _parse(raw: dict) -> dict:
    return raw


async def _fake_fetch_json(session, url, retries, backoff_base):
    pid = url.rsplit("/", 1)[-1]
    if pid == "404":
        raise NotFoundError(url)
    if pid == "500":
        raise FetchError(url)
    if pid == "blocked":
        raise BlockedError(url)
    return {"id": int(pid), "name": "n", "url_key": "k", "price": 1, "images": []}


class _FakeSession:
    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


def _make_config(tmp_path: Path, **overrides) -> FetchConfig:
    defaults = dict(
        url_template="http://x/{id}",
        parse=_parse,
        required_fields=("id", "name", "url_key", "price", "images"),
        output_dir=tmp_path / "output",
        logs_dir=tmp_path / "logs",
        batch_size=2,
        concurrency=5,
    )
    defaults.update(overrides)
    return FetchConfig(**defaults)


async def test_fetch_batch_splits_success_not_found_and_failed(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    config = _make_config(tmp_path)
    semaphore = asyncio.Semaphore(5)

    records, not_found, failed, blocked = await fetch_batch(None, semaphore, ["1", "404", "500"], config)

    assert [r["id"] for r in records] == [1]
    assert not_found == ["404"]
    assert failed == ["500"]
    assert blocked == []


async def test_fetch_batch_dedupes_duplicate_ids_within_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    config = _make_config(tmp_path)
    semaphore = asyncio.Semaphore(5)

    records, not_found, failed, blocked = await fetch_batch(None, semaphore, ["1", "1"], config)

    assert len(records) == 1


async def test_fetch_batch_routes_blocked_error_to_failed_and_blocked(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    config = _make_config(tmp_path)
    semaphore = asyncio.Semaphore(5)

    records, not_found, failed, blocked = await fetch_batch(None, semaphore, ["1", "blocked"], config)

    assert [r["id"] for r in records] == [1]
    assert failed == ["blocked"]
    assert blocked == ["blocked"]


async def test_run_pipeline_writes_batches_and_resumes(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    monkeypatch.setattr(pipeline_module.aiohttp, "ClientSession", _FakeSession)
    config = _make_config(tmp_path)
    ids = ["1", "2", "3", "4", "5"]

    stats = await run_pipeline(ids, config)
    assert stats.batches_total == 3
    assert stats.batches_skipped == 0
    assert stats.fetched == 5

    stats_again = await run_pipeline(ids, config)
    assert stats_again.batches_skipped == 3
    assert stats_again.fetched == 0


async def test_run_pipeline_logs_not_found_and_failed_ids(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    monkeypatch.setattr(pipeline_module.aiohttp, "ClientSession", _FakeSession)
    config = _make_config(tmp_path, batch_size=3)
    ids = ["1", "404", "500"]

    stats = await run_pipeline(ids, config)

    assert stats.not_found == 1
    assert stats.failed == 1
    not_found_log = (config.logs_dir / "not_found_ids.txt").read_text(encoding="utf-8")
    failed_log = (config.logs_dir / "failed_ids.txt").read_text(encoding="utf-8")
    assert not_found_log == "id\n404\n"
    assert failed_log == "id\n500\n"


def test_concurrency_ramp_yields_fibonacci_from_floor():
    ramp = pipeline_module._concurrency_ramp(3)
    assert [next(ramp) for _ in range(6)] == [3, 5, 8, 13, 21, 34]


def _make_recording_semaphore(recorded: list[int]):
    class _RecordingSemaphore(asyncio.Semaphore):
        def __init__(self, value):
            recorded.append(value)
            super().__init__(value)

    return _RecordingSemaphore


async def test_run_pipeline_ramps_concurrency_up_on_clean_batches(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    monkeypatch.setattr(pipeline_module.aiohttp, "ClientSession", _FakeSession)
    recorded: list[int] = []
    monkeypatch.setattr(pipeline_module.asyncio, "Semaphore", _make_recording_semaphore(recorded))
    config = _make_config(tmp_path, batch_size=1, concurrency=3)
    ids = ["1", "2", "3", "4"]

    await run_pipeline(ids, config)

    assert recorded == [3, 5, 8, 13]


async def test_run_pipeline_resets_concurrency_to_floor_after_blocked_batch(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline_module, "fetch_json", _fake_fetch_json)
    monkeypatch.setattr(pipeline_module.aiohttp, "ClientSession", _FakeSession)
    recorded: list[int] = []
    monkeypatch.setattr(pipeline_module.asyncio, "Semaphore", _make_recording_semaphore(recorded))
    config = _make_config(tmp_path, batch_size=1, concurrency=3)
    ids = ["1", "blocked", "3"]

    stats = await run_pipeline(ids, config)

    assert recorded == [3, 5, 3]
    assert stats.blocked == 1
