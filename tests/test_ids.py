from pathlib import Path

from tiki_scraper.ids import is_valid_id, load_ids


def test_is_valid_id_accepts_positive_digit_strings():
    assert is_valid_id("138083218") is True
    assert is_valid_id(" 138083218 ") is True


def test_is_valid_id_rejects_bad_formats():
    assert is_valid_id("") is False
    assert is_valid_id("0") is False
    assert is_valid_id("007") is False
    assert is_valid_id("-5") is False
    assert is_valid_id("12a") is False
    assert is_valid_id("1.5") is False


def _write_csv(path: Path, ids: list[str]) -> None:
    lines = ["id"] + ids
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def test_load_ids_dedupes_within_and_across_files(tmp_path: Path):
    file_a = tmp_path / "a.csv"
    file_b = tmp_path / "b.csv"
    _write_csv(file_a, ["1", "2", "2", "bad", "3"])
    _write_csv(file_b, ["3", "4"])

    ids, stats = load_ids([file_a, file_b])

    assert ids == ["1", "2", "3", "4"]
    assert stats == {"total_read": 7, "invalid": 1, "duplicate": 2, "valid": 4}
