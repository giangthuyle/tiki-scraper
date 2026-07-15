from __future__ import annotations

import argparse
import os
from dataclasses import dataclass
from pathlib import Path

DEFAULT_INPUT_GLOB = "data/products-*.csv"


@dataclass
class Settings:
    input_paths: list[Path]
    output_dir: Path
    logs_dir: Path
    batch_size: int
    concurrency: int
    retries: int
    backoff_base: float
    adaptive_concurrency: bool
    proxy: str | None


def parse_args(argv: list[str] | None = None) -> Settings:
    parser = argparse.ArgumentParser(description="Fetch Tiki product-detail data")
    parser.add_argument("--input", nargs="+", default=None, help="input CSV file(s); defaults to data/products-*.csv")
    parser.add_argument("--output-dir", default="output")
    parser.add_argument("--logs-dir", default="logs")
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--concurrency", type=int, default=3, help="floor concurrency (or the fixed value with --fixed-concurrency)")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--backoff-base", type=float, default=2.0)
    parser.add_argument(
        "--fixed-concurrency",
        action="store_true",
        help="use --concurrency as a constant instead of ramping it up along the Fibonacci sequence",
    )
    parser.add_argument(
        "--proxy",
        default=os.environ.get("SCRAPER_PROXY"),
        help="proxy URL for outbound Tiki requests (default: $SCRAPER_PROXY); e.g. an IPRoyal residential endpoint",
    )
    args = parser.parse_args(argv)

    if args.input:
        input_paths = [Path(p) for p in args.input]
    else:
        input_paths = sorted(Path().glob(DEFAULT_INPUT_GLOB))

    return Settings(
        input_paths=input_paths,
        output_dir=Path(args.output_dir),
        logs_dir=Path(args.logs_dir),
        batch_size=args.batch_size,
        concurrency=args.concurrency,
        retries=args.retries,
        backoff_base=args.backoff_base,
        adaptive_concurrency=not args.fixed_concurrency,
        proxy=args.proxy,
    )
