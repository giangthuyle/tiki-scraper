from dispatch import batch_count


def test_batch_count_exact_and_remainder():
    assert batch_count(600000, 50) == 12000
    assert batch_count(100, 50) == 2
    assert batch_count(101, 50) == 3


def test_batch_count_zero():
    assert batch_count(0, 50) == 0
    assert batch_count(600000, 0) == 0
