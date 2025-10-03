"""Test functions common to various test modules."""

from beancount.core import data


def assert_txns_equal(a: list[data.Transaction], b: list[data.Transaction]):
    """Assert two lists of transactions represent the same transactions.

    Assertions ignore attributes including meta.
    """
    assert len(a) == len(b)
    attrs = ["payee", "narration", "date"]
    attrs_postings = ["account", "units"]
    for txn_a, txn_b in zip(a, b, strict=True):
        for attr in attrs:
            assert getattr(txn_a, attr) == getattr(txn_b, attr)
        assert len(txn_a.postings) == len(txn_b.postings)
        for post_a, post_b in zip(txn_a.postings, txn_b.postings, strict=True):
            for attr in attrs_postings:
                assert getattr(post_a, attr) == getattr(post_b, attr)
