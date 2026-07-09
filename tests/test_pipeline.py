import json
from pathlib import Path

from tiki_scraper.pipeline import (
    batch_is_done,
    batch_ranges,
    output_filename,
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
