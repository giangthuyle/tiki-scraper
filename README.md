# tiki-scraper

Fetches Tiki product-detail data for the product ids listed in `data/products-*.csv`
and stores the **full** Tiki product-detail JSON (every field the API returns, with
`id` normalized to an integer) as batched JSON files in `output/`.

Requests go through [CloakBrowser](https://pypi.org/project/cloakbrowser/) (a stealth
Chromium) rather than a plain HTTP client, because Tiki's WAF serves a JavaScript
challenge page instead of JSON to non-browser clients. Pages are long-lived and
reused across ids so the cookie earned by solving the challenge keeps working.

## Setup

    uv sync

## Run

    uv run tiki-scraper

Options (`uv run tiki-scraper --help`):

| Flag | Default | Meaning |
| --- | --- | --- |
| `--input` | all `data/products-*.csv` | one or more CSVs with an `id` column |
| `--output-dir` | `output/` | where batch JSON files are written |
| `--logs-dir` | `logs/` | where `not_found_ids.txt` / `failed_ids.txt` are written |
| `--batch-size` | `1000` | ids per output file |
| `--concurrency` | `3` | number of persistent browser pages fetching in parallel |
| `--retries` | `3` | retry attempts per request on 5xx/429/timeout/challenge page |
| `--backoff-base` | `2.0` | seconds; exponential backoff base between retries |
| `--proxy` | `$SCRAPER_PROXY` | proxy URL for outbound Tiki requests |

Keep `--concurrency` low. Each unit is a live Chromium tab (~50–80 MB), not a cheap
socket, so the pool size is fixed for the whole run and sized up front.

### Resume

Re-running the same command resumes automatically: any
`output/products_<start>-<end>.json` that exists and parses as a JSON array is
treated as already attempted and is not re-fetched.

- Ids that returned 404 land in `logs/not_found_ids.txt` (the product no longer
  exists — not an error).
- Ids that failed after exhausting retries land in `logs/failed_ids.txt`.

Both log files start with an `id` header, so each is a valid `--input` CSV on its
own. Re-run just the failures with:

    uv run tiki-scraper --input logs/failed_ids.txt --output-dir output2

After each run the CLI verifies the output directory and reports the total record
count plus any duplicate ids across files.

## Tests

    uv run pytest

## Residential proxy — getting past the WAF from cloud IPs

Tiki blocks datacenter egress (Azure, VPS), so a **residential proxy** is required
when scraping from anywhere but a home connection. Providers such as IPRoyal or
Decodo expose a single rotating gateway. Pass it via `SCRAPER_PROXY` (rather than a
global `HTTPS_PROXY`, which would also tunnel Azure SDK traffic):

    SCRAPER_PROXY='http://USER:PASS_country-vn@geo.iproyal.com:12321' \
      uv run tiki-scraper --concurrency 1

- `_country-vn` after the password pins Vietnamese exit IPs (lower latency, less
  suspicious). Rotating is the default — one new IP per request. For a sticky IP,
  append `_session-<id>_lifetime-10m`.
- If the credentials contain characters that break shell quoting, build the URL with
  the helper, which reads `USER_PROXY` / `PASSWORD_PROXY` from `.env` and
  URL-encodes them:

      export SCRAPER_PROXY="$(uv run python scripts/mkproxy.py)"

Leaving `SCRAPER_PROXY` unset means direct connections (the default). Start at
`--concurrency 1` — residential bandwidth is billed per GB — and raise it while
nothing gets blocked.

## Azure deployment (queue + multi-region)

Requires: Azure CLI (`az login` done), Terraform >= 1.5, Git LFS.

    git lfs pull                 # fetch data/products-*.csv (stored in LFS)
    cd infra
    terraform init
    terraform apply              # hub storage (queue + output) + 4 Function Apps

Enqueue every batch (run from the repo root — counting batches needs the local CSVs):

    export HUB_STORAGE=$(cd infra && terraform output -raw hub_connection_string)
    uv run python dispatch.py --dry-run    # sanity check: 12000 batches (batch_size=50)
    uv run python dispatch.py              # enqueue 0..11999 onto queue "batches"

Four Function Apps in southeastasia / eastasia / japaneast / koreacentral drain the
same queue — one egress IP per region, spreading WAF risk — and write JSON back to
the hub storage `output` container. The queue retries failed messages; permanently
broken ones land in `batches-poison`. Re-running `dispatch.py` is safe: batches that
already produced output are skipped. Inspect results with:

    ACCOUNT=$(cd infra && terraform output -raw hub_storage_account)
    KEY=$(az storage account keys list -g tikiscraper-rg -n "$ACCOUNT" --query "[0].value" -o tsv)
    az storage blob list --account-name "$ACCOUNT" --account-key "$KEY" \
      --container-name output --query "[].name" -o tsv

Pass the proxy to all four regions at apply time:

    terraform apply -var 'scraper_proxy=http://USER:PASS_country-vn@geo.iproyal.com:12321'

Tear down with `cd infra && terraform destroy`.

> **Note:** the Azure path was built when the scraper used a plain HTTP client. Since
> the switch to CloakBrowser it needs a Chromium runtime inside the Function App,
> which the current Terraform does not provision — treat the deployment as untested
> until that is sorted (a container-based plan is the likely fix). Local runs are the
> supported path today.

## Layout

    src/tiki_scraper/     CLI, config, id loading, fetch client, batch pipeline
    tests/                pytest suite (no network)
    infra/                Terraform: hub storage + queue + 4 regional Function Apps
    batches.py            global batch-id -> id-slice mapping (shared by dispatcher and function)
    dispatch.py           enqueues batch ids onto the hub queue
    function_app.py       Azure Functions queue trigger: scrape one batch, upload to blob
    scripts/mkproxy.py    builds SCRAPER_PROXY from .env credentials
