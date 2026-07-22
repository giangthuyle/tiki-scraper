from pathlib import Path

import psycopg

from tiki_scraper.load_db import load_output_dir, read_batch, upsert_batch


class FakeCopy:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def write_row(self, row):
        if self.conn.fail_writes:
            raise psycopg.Error("simulated copy failure")
        self.conn.written.append(row)


class FakeCursor:
    def __init__(self, conn):
        self.conn = conn

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def copy(self, query):
        return FakeCopy(self.conn)

    def execute(self, query, params=None):
        self.conn.executed.append(query)


class FakeConn:
    def __init__(self, fail_writes=False, fail_rollback=False):
        self.fail_writes = fail_writes
        self.fail_rollback = fail_rollback
        self.written = []
        self.executed = []
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return FakeCursor(self)

    def commit(self):
        self.committed = True

    def rollback(self):
        if self.fail_rollback:
            raise psycopg.Error("connection already dead")
        self.rolled_back = True


def test_read_batch_missing_file_returns_empty(tmp_path: Path):
    assert read_batch(tmp_path / "missing.json") == []


def test_read_batch_corrupt_json_returns_empty(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text("not json", encoding="utf-8")
    assert read_batch(path) == []


def test_read_batch_non_list_returns_empty(tmp_path: Path):
    path = tmp_path / "bad.json"
    path.write_text('{"id": 1}', encoding="utf-8")
    assert read_batch(path) == []


def test_upsert_batch_skips_records_without_id():
    conn = FakeConn()
    n = upsert_batch(conn, [{"id": 1, "name": "a"}, {"name": "no id"}])
    assert n == 1
    assert len(conn.written) == 1
    assert conn.committed is True


def test_upsert_batch_copies_then_upserts_then_truncates():
    conn = FakeConn()
    upsert_batch(conn, [{"id": 1, "name": "a"}])
    assert any("INSERT INTO products" in q for q in conn.executed)
    assert any("TRUNCATE" in q for q in conn.executed)


def test_upsert_batch_rolls_back_on_db_error():
    conn = FakeConn(fail_writes=True)
    n = upsert_batch(conn, [{"id": 1, "name": "a"}])
    assert n == 0
    assert conn.rolled_back is True


def test_upsert_batch_survives_a_dead_connection():
    conn = FakeConn(fail_writes=True, fail_rollback=True)
    n = upsert_batch(conn, [{"id": 1, "name": "a"}])
    assert n == 0


def test_load_output_dir_counts_loaded_and_skipped(tmp_path: Path):
    (tmp_path / "products_0000000-0000001.json").write_text(
        '[{"id": 1}, {"id": 2}]', encoding="utf-8"
    )
    (tmp_path / "products_0000002-0000002.json").write_text("not json", encoding="utf-8")

    conn = FakeConn()
    loaded, skipped_files = load_output_dir(conn, tmp_path)
    assert loaded == 2
    assert skipped_files == 1
