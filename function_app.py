from __future__ import annotations

import sys
from pathlib import Path

# tiki_scraper sống trong src/ — thêm vào path để deployment zip import được
# (không đóng gói thành wheel, tránh bước build package trong Oryx).
sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

import asyncio
import json
import logging
import os
import tempfile

import azure.functions as func
from azure.storage.blob import BlobServiceClient

from batches import BATCH_SIZE, batch_slice, parse_batch_id
from tiki_scraper.pipeline import output_filename, run_pipeline
from tiki_scraper.product import build_config

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

    try:
        start, end, ids = batch_slice(batch_id)
    except IndexError as exc:
        return func.HttpResponse(str(exc), status_code=400)

    target = output_filename(start, end)
    blob_service = BlobServiceClient.from_connection_string(os.environ["AzureWebJobsStorage"])
    container = blob_service.get_container_client(OUTPUT_CONTAINER)
    try:
        container.create_container()
    except Exception:
        pass  # đã tồn tại

    # Idempotent: batch đã có output thì bỏ qua (resume mức batch).
    # Container đã tên "output" nên blob đặt tên trần `target` (không thêm
    # tiền tố "output/", tránh path output/output/...).
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

        # pipeline đặt tên file theo chỉ số LOCAL (0..len-1) nên mọi batch_id
        # trùng tên — upload lại dưới tên GLOBAL `target` để không đè nhau.
        produced = list((tmp_path / "output").glob("products_*.json"))
        if produced:
            with produced[0].open("rb") as f:
                container.get_blob_client(target).upload_blob(f, overwrite=True)

        # log tách theo batch_id (upload, không append) để gọi song song
        # nhiều batch không tranh chấp cùng một blob.
        for name, folder in (("not_found_ids.txt", "not_found_ids"), ("failed_ids.txt", "failed_ids")):
            p = tmp_path / "logs" / name
            if p.exists():
                container.get_blob_client(f"logs/{folder}/{batch_id}.txt").upload_blob(
                    p.read_bytes(), overwrite=True
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
