"""Common pytest fixtures and hooks."""

from collections import abc
import contextlib
import datetime
import io
import os
from pathlib import Path
import shutil
import sys
import textwrap
import typing

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


def set_cl_args(cl: str):
    """Set system command line arguments.

    Parameters
    ----------
    cl
        String representing command passed to command line, for example
        'beanahead exp x rx'
    """
    args = cl.split(" ")
    args.insert(0, "beanahead")
    sys.argv = args


def get_fileobj(filepath: Path, mode="r") -> io.TextIOWrapper:
    return filepath.open(mode, encoding=ENCODING)


def get_entries_from_string(string: str) -> data.Entries:
    """Get entries as parsed from a string."""
    string = textwrap.dedent(string)
    entries, _, _ = beancount.loader.load_string(string)
    return entries


def get_expected_output(string: str):
    """Convert raw triple quoted string to string representing expected output."""
    return textwrap.dedent(string)[1:]


def also_get_stdout(f: abc.Callable, *args, **kwargs) -> tuple[typing.Any, str]:
    """Return a function's return together with output to stdout."""
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rtrn = f(*args, **kwargs)
    return rtrn, stdout.getvalue()


@pytest.fixture
def encoding() -> abc.Iterator[str]:
    yield ENCODING


@pytest.fixture
def temp_dir() -> abc.Iterator[Path]:
    yield TEMP_DIR


@pytest.fixture
def cwd_as_temp_dir(temp_dir) -> abc.Iterator[Path]:
    """Set cwd to `tests._temp` over fixture's duration.

    Yields temporary cwd.
    """
    prev_cwd = Path.cwd()
    os.chdir(temp_dir)
    yield Path.cwd()
    os.chdir(prev_cwd)


def _clean_test_dir():
    """Remove all files and directories from the test directory"""
    assert TEMP_DIR.is_dir()
    for dirpath, dirname, filenames in os.walk(TEMP_DIR):
        for filename in filenames:
            path = Path(dirpath) / filename
            os.remove(path)


def pytest_sessionstart(session):
    """Hook executed before session starts.

    Clean temporary test folder.
    """
    _clean_test_dir()


@pytest.fixture
def clean_test_dir() -> abc.Iterator[Path]:
    _clean_test_dir()
    yield


@pytest.fixture
def mock_input(monkeypatch) -> abc.Iterator:
    """Mock built-in input command to return pre-defined responses."""

    class MockInput:
        def __init__(self, responses: abc.Generator[str]):
            self.responses = responses
            monkeypatch.setattr("beanahead.utils.get_input", self.input)

        def input(self, string: str) -> str:
            print(string)
            return next(self.responses)

    yield MockInput


@pytest.fixture
def res_dir() -> abc.Iterator[Path]:
    yield TEST_ROOT / "resources"


@pytest.fixture
def recon_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "recon"


# Common fixtures from files in recon folder


@pytest.fixture
def filepath_recon_x(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "x.beancount"


@pytest.fixture
def filepath_recon_rx(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "rx.beancount"


@pytest.fixture
def filepath_recon_extraction(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "extraction.beancount"


@pytest.fixture
def filepaths_recon_copy(
    filepath_recon_extraction, filepath_recon_rx, filepath_recon_x, temp_dir
) -> abc.Iterator[dict[str, Path]]:
    """Filepaths to copies of files before reconciling new transactions.

    Copies of each file saved to temporary folder.

    Yields mapping to temporary paths with keys as:
        "extraction" - file representing extracted transactions
        "rx" - expected regular transactions ledger
        "x" - expected transactions ledger
    """
    d = {}
    for k, filepath in zip(
        ("extraction", "rx", "x"),
        (filepath_recon_extraction, filepath_recon_rx, filepath_recon_x),
    ):
        string = shutil.copy(filepath, temp_dir)
        d[k] = Path(string)
    yield d
    for path in d.values():
        path.unlink()


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
