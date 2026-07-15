# tiki-scraper

Fetches Tiki product-detail data for the product ids listed in
`data/products-*.csv` and saves the **full** Tiki product-detail JSON (every field the API
returns, with `id` normalized to an integer) as batched JSON files in
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
- `--concurrency` — floor/starting concurrency (default: `3`). By default
  this ramps up along the Fibonacci sequence (3, 5, 8, 13, 21, ...) after
  each batch with no blocks, and resets to the floor the moment a batch
  hits Tiki's WAF (a 200 response with an HTML body instead of JSON).
- `--fixed-concurrency` — pin `--concurrency` as a constant instead of
  ramping it up (e.g. `--concurrency 1 --fixed-concurrency` for the
  slowest, most conservative rate).
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

## Deploy lên Azure (Terraform)

Cần: Azure CLI đã `az login`, Terraform >= 1.5, và Git LFS.

Các file `data/products-*.csv` (danh sách id) được track qua **Git LFS** — sau
khi clone phải `git lfs pull` để lấy nội dung thật; nếu không, zip deploy chỉ
đóng gói con trỏ LFS và function sẽ trả HTTP 500 ("no product ids deployed").

    git lfs pull
    cd infra
    terraform init
    terraform apply      # tạo RG, Storage, Consumption plan, Function App + zip-deploy code

Sau khi apply, gọi một batch (batch_id 0..5999, mỗi batch 100 id):

    HOST=$(terraform output -raw function_hostname)
    KEY=$(az functionapp keys list -g tikiscraper-rg -n tikiscraper-func --query functionKeys.default -o tsv)
    curl -X POST "https://$HOST/api/scrape?code=$KEY" \
      -H 'content-type: application/json' -d '{"batch_id": 0}'

Kết quả JSON ghi vào container Blob `output/` (`output/products_<start>-<end>.json`);
id 404 → `logs/not_found_ids/<batch_id>.txt`, id lỗi → `logs/failed_ids/<batch_id>.txt`.
Gọi lại cùng `batch_id` khi output đã có → trả `already_done` (idempotent).
