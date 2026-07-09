from pathlib import Path

import pytest

from tiki_scraper.cli import main


def test_main_exits_when_no_input_files_found(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        main([])
