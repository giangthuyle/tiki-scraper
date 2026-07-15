from __future__ import annotations

from pathlib import Path

from .pipeline import FetchConfig

PRODUCT_URL_TEMPLATE = "https://api.tiki.vn/product-detail/api/v1/products/{id}"
REQUIRED_FIELDS: tuple[str, ...] = ("id",)


def parse_product(raw: dict) -> dict:
    # Keep the Tiki product-detail response intact (every field); only coerce
    # id to int since the pipeline uses it as the dedup key and validate_record
    # compares it against the requested id.
    return {**raw, "id": int(raw["id"])}


def build_config(
    output_dir: Path,
    logs_dir: Path,
    batch_size: int,
    concurrency: int,
    retries: int,
    backoff_base: float,
    adaptive_concurrency: bool = True,
    proxy: str | None = None,
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
        adaptive_concurrency=adaptive_concurrency,
        proxy=proxy,
    )
