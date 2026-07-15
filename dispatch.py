#!/usr/bin/env python3
"""Enqueue scraper batch ids onto the shared hub Storage Queue so the regional
Function Apps drain them. Run locally (needs the hub connection string).

  HUB_STORAGE='<conn>' python dispatch.py              # enqueue all batches
  HUB_STORAGE='<conn>' python dispatch.py --dry-run     # just print the count
  python dispatch.py --connection '<conn>' --start 500  # resume from a batch id
"""
from __future__ import annotations

import argparse
import math
import os

from batches import all_ids


def batch_count(total: int, batch_size: int) -> int:
    if batch_size <= 0:
        return 0
    return math.ceil(total / batch_size)


def main() -> None:
    ap = argparse.ArgumentParser(description="Enqueue scraper batch ids")
    ap.add_argument("--batch-size", type=int, default=50, help="must match the deployed BATCH_SIZE")
    ap.add_argument("--queue", default=os.environ.get("QUEUE_NAME", "batches"))
    ap.add_argument("--connection", default=os.environ.get("HUB_STORAGE"))
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    n = batch_count(len(all_ids()), args.batch_size)
    print(f"{n} batches total (batch_size={args.batch_size}); enqueueing {args.start}..{n - 1}")
    if args.dry_run:
        return
    if not args.connection:
        raise SystemExit("set HUB_STORAGE env or pass --connection (hub storage connection string)")

    from azure.storage.queue import QueueClient, TextBase64EncodePolicy

    q = QueueClient.from_connection_string(
        args.connection, args.queue, message_encode_policy=TextBase64EncodePolicy()
    )
    sent = 0
    for batch_id in range(args.start, n):
        q.send_message(str(batch_id))
        sent += 1
    print(f"enqueued {sent} messages to '{args.queue}'")


if __name__ == "__main__":
    main()
