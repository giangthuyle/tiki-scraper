from pathlib import Path

from tiki_scraper.product import PRODUCT_URL_TEMPLATE, build_config, parse_product

_RAW = {
    "id": 138083218,
    "name": "Do Choi Xep Hinh",
    "url_key": "do-choi-xep-hinh-p138083218",
    "price": 268000,
    "description": "<p><strong>Mo ta</strong> san pham</p>",
    "images": [
        {"base_url": "https://salt.tikicdn.com/a.png", "large_url": "https://salt.tikicdn.com/large/a.png"},
        {"large_url": "https://salt.tikicdn.com/large/b.png"},
    ],
}


def test_parse_product_maps_and_normalizes_fields():
    record = parse_product(_RAW)

    assert record == {
        "id": 138083218,
        "name": "Do Choi Xep Hinh",
        "url_key": "do-choi-xep-hinh-p138083218",
        "price": 268000,
        "description": "Mo ta san pham",
        "images": ["https://salt.tikicdn.com/a.png"],
    }


def test_parse_product_handles_missing_images_key():
    raw = dict(_RAW, images=None)
    record = parse_product(raw)
    assert record["images"] == []


def test_build_config_wires_product_url_and_parser(tmp_path: Path):
    config = build_config(
        output_dir=tmp_path / "output",
        logs_dir=tmp_path / "logs",
        batch_size=100,
        concurrency=10,
        retries=2,
        backoff_base=1.0,
    )

    assert config.url_template == PRODUCT_URL_TEMPLATE
    assert config.parse is parse_product
    assert config.required_fields == ("id", "name", "url_key", "price", "images")
    assert config.batch_size == 100
