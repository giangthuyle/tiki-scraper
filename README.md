# tiki-scraper

Fetches Tiki product-detail data for the product ids listed in
`data/products-*.csv` and saves normalized records (`id`, `name`,
`url_key`, `price`, `description`, `images`) as batched JSON files in
`output/`.

## Setup

    uv sync

## Run

    uv run tiki-scraper

Options (see `uv run tiki-scraper --help`):

- `--input` — one or more CSV files with an `id` column (default: all `data/products-*.csv`)
- `--output-dir` — where batch JSON files are written (default: `output/`)
- `--logs-dir` — where `not_found_ids.txt` / `failed_ids.txt` are written (default: `logs/`)
- `--batch-size` — ids per output file (default: `1000`)
- `--concurrency` — max in-flight requests (default: `50`)
- `--retries` — retry attempts per request on network error/5xx/429 (default: `3`)
- `--backoff-base` — seconds, exponential backoff base between retries (default: `2.0`)

Re-running the same command resumes automatically: any `output/products_<start>-<end>.json`
that already exists and parses as a JSON array is treated as already
attempted and is not re-fetched. Ids that returned 404 are recorded in
`logs/not_found_ids.txt` (product no longer exists — not an error). Ids
that failed after exhausting retries are recorded in `logs/failed_ids.txt`.
Both log files start with an `id` header, so they're valid `--input` CSVs
on their own — re-run just the failures with
`uv run tiki-scraper --input logs/failed_ids.txt --output-dir output2`.

## Tests

    uv run pytest
