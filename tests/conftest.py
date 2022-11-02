"""Common pytest fixtures and hooks."""

from collections import abc
import datetime
import io
import os
from pathlib import Path
import textwrap

import beancount
from beancount.core import data
import pytest


# pylint: disable=missing-function-docstring, missing-type-doc
# pylint: disable=missing-param-doc, missing-any-param-doc, redefined-outer-name
# pylint: disable=too-many-public-methods, too-many-arguments, too-many-locals
# pylint: disable=too-many-statements
# pylint: disable=protected-access, line-too-long, unused-argument, invalid-name
#   missing-fuction-docstring: doc not required for all tests
#   protected-access: not required for tests
#   not compatible with use of fixtures to parameterize tests:
#       too-many-arguments, too-many-public-methods
#   not compatible with pytest fixtures:
#       redefined-outer-name, missing-any-param-doc, missing-type-doc
#   unused-argument: not compatible with pytest fixtures, caught by pylance anyway.
#   invalid-name: names in tests not expected to strictly conform with snake_case.


TEST_ROOT = Path(__file__).parent
TEMP_DIR = TEST_ROOT / r"./_temp"
ENCODING = "utf-8"


def get_fileobj(filepath: Path, mode="r") -> io.TextIOWrapper:
    return filepath.open(mode, encoding=ENCODING)


def get_entries_from_string(string: str) -> data.Entries:
    """Get entries as parsed from a string."""
    string = textwrap.dedent(string)
    entries, _, _ = beancount.loader.load_string(string)
    return entries


@pytest.fixture
def encoding() -> abc.Iterator[str]:
    yield ENCODING


@pytest.fixture
def temp_dir() -> abc.Iterator[Path]:
    yield TEMP_DIR


def pytest_sessionstart(session):
    """Hook executed before session starts.

    Clean temporary test folder.
    """
    assert TEMP_DIR.is_dir()
    for dirpath, dirname, filenames in os.walk(TEMP_DIR):
        for filename in filenames:
            path = Path(dirpath) / filename
            os.remove(path)


@pytest.fixture
def res_dir() -> abc.Iterator[Path]:
    yield TEST_ROOT / "resources"


@pytest.fixture
def recon_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "recon"


# Common fixtures from files in recon folder


@pytest.fixture
def filepath_recon_rx(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "rx.beancount"


# Common fixtures from files in resources folder


@pytest.fixture
def filepath_ledger_txns(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_ledger_txns.beancount"


@pytest.fixture
def filepath_rx(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_rx.beancount"


@pytest.fixture
def txns_ledger(filepath_ledger_txns) -> abc.Iterator[list[data.Transaction]]:
    txns, errors, options = beancount.loader.load_file(filepath_ledger_txns)
    yield txns


@pytest.fixture
def txn(txns_ledger) -> abc.Iterator[data.Transaction]:
    yield txns_ledger[0]


@pytest.fixture
def txns_rx(filepath_rx) -> abc.Iterator[list[data.Transaction]]:
    txns, errors, options = beancount.loader.load_file(filepath_rx)
    yield txns


@pytest.fixture
def rx_txn_edison(txns_rx) -> abc.Iterator[data.Transaction]:
    txn = txns_rx[1]
    assert txn.payee == "EDISON"
    assert txn.date == datetime.date(2022, 10, 5)
    yield txn


@pytest.fixture
def rx_txn_chase(txns_rx) -> abc.Iterator[data.Transaction]:
    txn = txns_rx[-1]
    assert txn.payee == "Chase"
    assert txn.date == datetime.date(2022, 10, 31)
    yield txn
