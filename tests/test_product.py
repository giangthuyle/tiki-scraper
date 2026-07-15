from tiki_scraper.product import REQUIRED_FIELDS, parse_product


def test_parse_product_keeps_all_fields_and_int_id():
    raw = {"id": "42", "name": "x", "inventory": {"qty": 3}, "extra": [1, 2]}
    out = parse_product(raw)
    assert out["id"] == 42
    assert out["name"] == "x"
    assert out["inventory"] == {"qty": 3}
    assert out["extra"] == [1, 2]


def test_parse_product_does_not_mutate_input():
    raw = {"id": "7"}
    parse_product(raw)
    assert raw["id"] == "7"


def test_required_fields_is_just_id():
    assert REQUIRED_FIELDS == ("id",)
