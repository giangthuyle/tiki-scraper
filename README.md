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

## Deploy lên Azure (queue + multi-region)

Cần: Azure CLI đã `az login`, Terraform >= 1.5, Git LFS.

    git lfs pull                 # lấy data/products-*.csv (LFS)
    cd infra
    terraform init
    terraform apply              # HUB storage (queue+output) + 4 Function App (4 region)

Enqueue toàn bộ batch (chạy từ repo root, cần data local để đếm số batch):

    export HUB_STORAGE=$(cd infra && terraform output -raw hub_connection_string)
    uv run python dispatch.py --dry-run    # kiểm tra: 12000 batches (batch_size=50)
    uv run python dispatch.py              # enqueue 0..11999 vào queue "batches"

4 Function App ở southeastasia/eastasia/japaneast/koreacentral cùng rút queue
(mỗi region một IP egress khác → phân tán rủi ro WAF), scrape rồi ghi JSON về
container `output` của HUB storage. Queue tự retry message lỗi; message hỏng
rơi vào `batches-poison`. Chạy lại `dispatch.py` an toàn — batch đã có output
được bỏ qua (idempotent). Xem kết quả:

    KEY=$(az storage account keys list -g tikiscraper-rg -n $(cd infra && terraform output -raw hub_storage_account) --query "[0].value" -o tsv)
    az storage blob list --account-name $(cd infra && terraform output -raw hub_storage_account) --account-key "$KEY" --container-name output --query "[].name" -o tsv

Dọn: `cd infra && terraform destroy`.
