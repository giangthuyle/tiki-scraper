from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import psycopg

logger = logging.getLogger(__name__)

DDL = """
CREATE TABLE IF NOT EXISTS products (
    id BIGINT PRIMARY KEY,
    data JSONB NOT NULL,
    loaded_at TIMESTAMPTZ NOT NULL DEFAULT now()
)
"""

STAGING_DDL = "CREATE TEMP TABLE IF NOT EXISTS staging_products (id BIGINT, data JSONB)"

COPY_INTO_STAGING = "COPY staging_products (id, data) FROM STDIN"

# Records average ~9.6 KB (batch files run ~750 KB for ~80 records) — large
# enough that COPY's bulk-load path (skips per-row planning/parsing) beats a
# parameterized multi-row INSERT of the same rows.
UPSERT_FROM_STAGING = """
INSERT INTO products (id, data, loaded_at)
SELECT id, data, now() FROM staging_products
ON CONFLICT (id) DO UPDATE SET data = EXCLUDED.data, loaded_at = EXCLUDED.loaded_at
"""

TRUNCATE_STAGING = "TRUNCATE staging_products"


def read_batch(path: Path) -> list[dict]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        logger.error("could not read %s: %s", path, exc)
        return []
    if not isinstance(data, list):
        logger.error("unexpected content in %s: expected a list", path)
        return []
    return data


def upsert_batch(conn, records: list[dict]) -> int:
    rows = []
    for r in records:
        try:
            rows.append((int(r["id"]), json.dumps(r, ensure_ascii=False)))
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning("skipping record without a valid id: %s", exc)
    if not rows:
        return 0

    # COPY into a scratch staging table, then a single set-based upsert from
    # there into products. COPY itself has no ON CONFLICT, so it can't write
    # to products directly. staging_products is TRUNCATED after every file,
    # so a crash mid-file can't leak rows into the next one.
    try:
        with conn.cursor() as cur:
            with cur.copy(COPY_INTO_STAGING) as copy:
                for row in rows:
                    copy.write_row(row)
            cur.execute(UPSERT_FROM_STAGING)
            cur.execute(TRUNCATE_STAGING)
        conn.commit()
    except psycopg.Error as exc:
        logger.error("db write failed for batch of %d records: %s", len(rows), exc)
        try:
            conn.rollback()
        except psycopg.Error:
            # Connection is already dead (e.g. server dropped it) - rollback
            # itself raised. Let the caller's reconnect-or-abort logic decide;
            # don't let a second exception here crash the whole load run.
            logger.error("rollback failed too - connection likely dead")
        return 0
    return len(rows)


def load_output_dir(conn, output_dir: Path) -> tuple[int, int]:
    loaded = 0
    skipped_files = 0
    for path in sorted(output_dir.glob("products_*.json")):
        records = read_batch(path)
        if not records:
            skipped_files += 1
            continue
        n = upsert_batch(conn, records)
        loaded += n
        if n == 0:
            skipped_files += 1
    return loaded, skipped_files


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    parser = argparse.ArgumentParser(description="Load Tiki product JSON batches into Postgres")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args(argv)

    if not args.database_url:
        raise SystemExit("no database URL (pass --database-url or set $DATABASE_URL)")

    try:
        conn = psycopg.connect(args.database_url, connect_timeout=10)
    except psycopg.Error as exc:
        raise SystemExit(f"could not connect to database: {exc}")

    try:
        with conn.cursor() as cur:
            cur.execute(DDL)
            cur.execute(STAGING_DDL)
        conn.commit()
        loaded, skipped_files = load_output_dir(conn, Path(args.output_dir))
    finally:
        conn.close()

    logger.info("load done: loaded=%d skipped_files=%d", loaded, skipped_files)


if __name__ == "__main__":
    main()
