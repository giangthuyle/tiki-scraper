from __future__ import annotations

import sys
from pathlib import Path

# tiki_scraper lives in src/ — add to path so the deployment zip can import it
# (not packaged as a wheel, avoids an Oryx build step for the local package).
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import asyncio
import json
import logging
import os
import tempfile

import azure.functions as func
from azure.core.exceptions import ResourceExistsError
from azure.storage.blob import BlobServiceClient

from batches import all_ids, batch_slice
from tiki_scraper.pipeline import output_filename, run_pipeline
from tiki_scraper.product import build_config

app = func.FunctionApp()
logger = logging.getLogger(__name__)

HUB_STORAGE = "HUB_STORAGE"  # app-setting name holding the hub connection string
OUTPUT_CONTAINER = os.environ.get("OUTPUT_CONTAINER", "output")


def _hub_container():
    service = BlobServiceClient.from_connection_string(os.environ[HUB_STORAGE])
    container = service.get_container_client(OUTPUT_CONTAINER)
    try:
        container.create_container()
    except ResourceExistsError:
        pass
    return container


def process_batch(batch_id: int) -> dict:
    """Scrape one batch and upload its JSON + logs to the hub blob container.
    Idempotent: returns early if the output blob already exists. Raises on a
    hard failure so the queue trigger retries the message."""
    if not all_ids():
        raise RuntimeError("no product ids deployed (data/products-*.csv missing from package)")

    start, end, ids = batch_slice(batch_id)
    target = output_filename(start, end)
    container = _hub_container()

    if container.get_blob_client(target).exists():
        return {"status": "already_done", "batch_id": batch_id, "blob": target}

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        config = build_config(
            output_dir=tmp_path / "output",
            logs_dir=tmp_path / "logs",
            batch_size=len(ids),  # one internal batch; slice is already <= BATCH_SIZE
            concurrency=int(os.environ.get("CONCURRENCY", "3")),
            retries=int(os.environ.get("RETRIES", "3")),
            backoff_base=float(os.environ.get("BACKOFF_BASE", "2.0")),
        )
        stats = asyncio.run(run_pipeline(ids, config))

        # pipeline names files by LOCAL index; upload under the GLOBAL name so
        # batches don't collide in the shared container.
        produced = list((tmp_path / "output").glob("products_*.json"))
        if produced:
            with produced[0].open("rb") as f:
                container.get_blob_client(target).upload_blob(f, overwrite=True)

        for name, folder in (("not_found_ids.txt", "not_found_ids"), ("failed_ids.txt", "failed_ids")):
            p = tmp_path / "logs" / name
            if p.exists():
                container.get_blob_client(f"logs/{folder}/{batch_id}.txt").upload_blob(
                    p.read_bytes(), overwrite=True
                )

    return {
        "status": "done",
        "batch_id": batch_id,
        "blob": target,
        "fetched": stats.fetched,
        "not_found": stats.not_found,
        "failed": stats.failed,
        "blocked": stats.blocked,
    }


@app.queue_trigger(arg_name="msg", queue_name="%QUEUE_NAME%", connection="HUB_STORAGE")
def scrape_queue(msg: func.QueueMessage) -> None:
    batch_id = int(msg.get_body().decode())
    result = process_batch(batch_id)
    logger.info("batch %s -> %s", batch_id, json.dumps(result))
