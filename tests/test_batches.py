import pytest

from batches import batch_bounds


def test_batch_bounds_full_batches():
    assert batch_bounds(0, 600000, 100) == (0, 99)
    assert batch_bounds(5999, 600000, 100) == (599900, 599999)


def test_batch_bounds_last_partial():
    assert batch_bounds(2, 250, 100) == (200, 249)


def test_batch_bounds_out_of_range_raises():
    with pytest.raises(IndexError):
        batch_bounds(6000, 600000, 100)
    with pytest.raises(IndexError):
        batch_bounds(-1, 600000, 100)

