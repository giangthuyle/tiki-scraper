# tiki-scraper

Fetches Tiki product-detail data for the product ids listed in `data/products-*.csv`
and stores the **full** Tiki product-detail JSON (every field the API returns, with
`id` normalized to an integer) as batched JSON files in `output/`.

Requests go through [CloakBrowser](https://pypi.org/project/cloakbrowser/) (a stealth
Chromium) rather than a plain HTTP client, because Tiki's WAF serves a JavaScript
challenge page instead of JSON to non-browser clients. Pages are long-lived and
reused across ids so the cookie earned by solving the challenge keeps working.

## Setup

    git lfs pull    # data/products-*.csv are stored in Git LFS
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

## Residential proxy (optional)

Direct connections are the default and work fine from a home connection. Tiki does
block datacenter egress, though, so if you run this from a VPS — or your own IP
starts getting served challenge pages — route requests through a **residential
proxy**. Providers such as IPRoyal or Decodo expose a single rotating gateway. Pass
it via `SCRAPER_PROXY` (rather than a global `HTTPS_PROXY`, so only Tiki requests are
tunnelled and your metered residential bandwidth isn't spent on anything else):

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

## Layout

    src/tiki_scraper/     CLI, config, id loading, fetch client, batch pipeline
    tests/                pytest suite (no network)
    data/                 product-id CSVs (tracked via Git LFS)
    scripts/mkproxy.py    builds SCRAPER_PROXY from .env credentials
