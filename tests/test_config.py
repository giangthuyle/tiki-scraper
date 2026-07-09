from pathlib import Path

from tiki_scraper.config import parse_args


def test_parse_args_defaults_glob_data_dir(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "data").mkdir()
    (tmp_path / "data" / "products-0-1.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "data" / "products-2-3.csv").write_text("id\n2\n", encoding="utf-8")

    settings = parse_args([])

    assert sorted(p.name for p in settings.input_paths) == [
        "products-0-1.csv",
        "products-2-3.csv",
    ]
    assert settings.output_dir == Path("output")
    assert settings.logs_dir == Path("logs")
    assert settings.batch_size == 1000
    assert settings.concurrency == 3
    assert settings.retries == 3
    assert settings.backoff_base == 2.0


def test_parse_args_explicit_input_and_overrides(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    csv_path = tmp_path / "custom.csv"
    csv_path.write_text("id\n1\n", encoding="utf-8")

    settings = parse_args(
        [
            "--input", str(csv_path),
            "--output-dir", "out2",
            "--logs-dir", "logs2",
            "--batch-size", "500",
            "--concurrency", "20",
            "--retries", "5",
            "--backoff-base", "1.5",
        ]
    )

    assert settings.input_paths == [csv_path]
    assert settings.output_dir == Path("out2")
    assert settings.logs_dir == Path("logs2")
    assert settings.batch_size == 500
    assert settings.concurrency == 20
    assert settings.retries == 5
    assert settings.backoff_base == 1.5


def test_parse_args_no_matching_files_returns_empty_list(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    settings = parse_args([])
    assert settings.input_paths == []
