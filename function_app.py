from __future__ import annotations

import sys
from pathlib import Path

# tiki_scraper lives under src/ — add it to the path so the deployment zip
# can import it (no wheel packaging, to avoid a build step in Oryx).
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import asyncio
import json
import logging
import os
import tempfile

import azure.functions as func
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

from batches import BATCH_SIZE, all_ids, batch_slice, parse_batch_id
from tiki_scraper.pipeline import output_filename, run_pipeline
from tiki_scraper.product import build_config

try:
    import uvloop

    uvloop.install()
except ImportError:
    pass

app = func.FunctionApp()
logger = logging.getLogger(__name__)

OUTPUT_CONTAINER = os.environ.get("OUTPUT_CONTAINER", "output")


@app.route(route="scrape", methods=["POST"])
def scrape(req: func.HttpRequest) -> func.HttpResponse:
    try:
        body = req.get_json() if req.get_body() else None
    except ValueError:
        body = None
    try:
        batch_id = parse_batch_id(body, dict(req.params))
    except ValueError as exc:
        return func.HttpResponse(str(exc), status_code=400)

    if not all_ids():
        return func.HttpResponse(
            "no product ids deployed (data/products-*.csv missing from package)",
            status_code=500,
        )

    try:
        start, end, ids = batch_slice(batch_id)
    except IndexError as exc:
        return func.HttpResponse(str(exc), status_code=400)

    target = output_filename(start, end)
    blob_service = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    container = blob_service.get_container_client(OUTPUT_CONTAINER)
    try:
        container.create_container()
    except ResourceExistsError:
        pass

    # Idempotent: skip batches that already have output (batch-level resume).
    # The container is already named "output", so blobs use the bare `target`
    # name (no "output/" prefix, to avoid an output/output/... path).
    if container.get_blob_client(target).exists():
        return func.HttpResponse(
            json.dumps({"status": "already_done", "batch_id": batch_id, "blob": target}),
            mimetype="application/json",
        )

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config = build_config(
            output_dir=tmp_path / "output",
            logs_dir=tmp_path / "logs",
            batch_size=BATCH_SIZE,
            concurrency=int(os.environ.get("CONCURRENCY", "3")),
            retries=int(os.environ.get("RETRIES", "3")),
            backoff_base=float(os.environ.get("BACKOFF_BASE", "2.0")),
        )
        stats = asyncio.run(run_pipeline(ids, config))

        # The pipeline names its file by LOCAL index (0..len-1), so every
        # batch_id collides — re-upload under the GLOBAL `target` name so
        # batches don't overwrite each other.
        produced = list((tmp_path / "output").glob("products_*.json"))
        if produced:
            with produced[0].open("rb") as f:
                container.get_blob_client(target).upload_blob(f, overwrite=True)

        # Logs are split by batch_id (upload, not append) so batches called
        # in parallel don't contend on the same blob.
        for name, folder in (("not_found_ids.txt", "not_found_ids"), ("failed_ids.txt", "failed_ids")):
            p = tmp_path / "logs" / name
            if p.exists():
                container.get_blob_client(f"logs/{folder}/{batch_id}.txt").upload_blob(
                    p.read_bytes(), overwrite=True
                )

    logger.info(
        "batch %s done: fetched=%d not_found=%d failed=%d blocked=%d",
        batch_id, stats.fetched, stats.not_found, stats.failed, stats.blocked,
    )
    return func.HttpResponse(
        json.dumps({
            "status": "done",
            "batch_id": batch_id,
            "blob": target,
            "fetched": stats.fetched,
            "not_found": stats.not_found,
            "failed": stats.failed,
            "blocked": stats.blocked,
        }),
        mimetype="application/json",
    )
