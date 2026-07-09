from __future__ import annotations

import asyncio
import logging

from .config import parse_args
from .ids import load_ids
from .pipeline import run_pipeline, verify_output
from .product import build_config

logger = logging.getLogger(__name__)


def main(argv: list[str] | None = None) -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    settings = parse_args(argv)
    if not settings.input_paths:
        raise SystemExit("no input CSV files found (pass --input or place files matching data/products-*.csv)")

    ids, id_stats = load_ids(settings.input_paths)
    logger.info(
        "input ids: total_read=%d invalid=%d duplicate=%d valid=%d",
        id_stats["total_read"], id_stats["invalid"], id_stats["duplicate"], id_stats["valid"],
    )

    try:
        import uvloop

        uvloop.install()
    except ImportError:
        pass

    config = build_config(
        output_dir=settings.output_dir,
        logs_dir=settings.logs_dir,
        batch_size=settings.batch_size,
        concurrency=settings.concurrency,
        retries=settings.retries,
        backoff_base=settings.backoff_base,
    )
    stats = asyncio.run(run_pipeline(ids, config))
    logger.info(
        "pipeline done: batches_total=%d batches_skipped=%d fetched=%d not_found=%d failed=%d",
        stats.batches_total, stats.batches_skipped, stats.fetched, stats.not_found, stats.failed,
    )

    total, duplicates = verify_output(settings.output_dir)
    if duplicates:
        logger.warning("verification: %d duplicate ids across %d total output records", duplicates, total)
    else:
        logger.info("verification: %d total output records, no duplicates", total)


if __name__ == "__main__":
    main()
