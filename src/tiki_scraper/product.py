from __future__ import annotations

from pathlib import Path

from .pipeline import FetchConfig
from .text import html_to_text

PRODUCT_URL_TEMPLATE = "https://api.tiki.vn/product-detail/api/v1/products/{id}"
REQUIRED_FIELDS: tuple[str, ...] = ("id", "name", "url_key", "price", "images")


def parse_product(raw: dict) -> dict:
    return {
        "id": int(raw["id"]),
        "name": (raw.get("name") or "").strip(),
        "url_key": (raw.get("url_key") or "").strip(),
        "price": raw.get("price"),
        "description": html_to_text(raw.get("description") or ""),
        "images": [img["base_url"] for img in (raw.get("images") or []) if img.get("base_url")],
    }


def build_config(
    output_dir: Path,
    logs_dir: Path,
    batch_size: int,
    concurrency: int,
    retries: int,
    backoff_base: float,
) -> FetchConfig:
    return FetchConfig(
        url_template=PRODUCT_URL_TEMPLATE,
        parse=parse_product,
        required_fields=REQUIRED_FIELDS,
        output_dir=output_dir,
        logs_dir=logs_dir,
        batch_size=batch_size,
        concurrency=concurrency,
        retries=retries,
        backoff_base=backoff_base,
    )
