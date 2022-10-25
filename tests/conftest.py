"""Common pytest fixtures and hooks."""

from collections import abc
import datetime
from pathlib import Path
import os
import shutil
import _io

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


def get_fileobj(filepath: Path, mode="r") -> _io.TextIOWrapper:
    return filepath.open(mode, encoding=ENCODING)


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
def make_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "make"


@pytest.fixture
def defs_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "defs"


@pytest.fixture
def recon_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "recon"


@pytest.fixture
def ans_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "answers"


@pytest.fixture
def cwd_as_temp_dir(temp_dir) -> abc.Iterator[Path]:
    """Set cwd to `tests._temp` over fixture's duration.

    Yields temporary cwd.
    """
    prev_cwd = Path.cwd()
    os.chdir(temp_dir)
    yield Path.cwd()
    os.chdir(prev_cwd)


@pytest.fixture
def cwd_as_make_dir(make_dir) -> abc.Iterator[Path]:
    """Set cwd to `tests.resources.make` over fixture's duration.

    Yields temporary cwd.
    """
    prev_cwd = Path.cwd()
    os.chdir(make_dir)
    yield Path.cwd()
    os.chdir(prev_cwd)


@pytest.fixture
def filepath_make_x(make_dir) -> abc.Iterator[Path]:
    yield make_dir / "x.beancount"


@pytest.fixture
def filepath_make_rx(make_dir) -> abc.Iterator[Path]:
    yield make_dir / "rx.beancount"


@pytest.fixture
def filepath_make_rx_def(make_dir) -> abc.Iterator[Path]:
    yield make_dir / "rx_def.beancount"


@pytest.fixture
def filepaths_make(
    filepath_make_x, filepath_make_rx, filepath_make_rx_def
) -> abc.Iterator[dict[str, Path]]:
    yield {
        "x": filepath_make_x,
        "rx": filepath_make_rx,
        "rx_def": filepath_make_rx_def,
    }


@pytest.fixture
def files_make(filepaths_make) -> abc.Iterator[dict[str, _io.TextIOWrapper]]:
    d = {k: get_fileobj(path) for k, path in filepaths_make.items()}
    yield d
    for fileobj in d.values():
        fileobj.close()


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
def filepath_ledger(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_ledger.beancount"


@pytest.fixture
def filepath_ledger_content(filepath_ledger, encoding) -> abc.Iterator[str]:
    yield filepath_ledger.read_text(encoding)


@pytest.fixture
def filepath_ledger_copy(filepath_ledger, temp_dir) -> abc.Iterator[Path]:
    string = shutil.copy(filepath_ledger, temp_dir)
    path = Path(string)
    yield path
    path.unlink()


@pytest.fixture
def filepath_ledger_txns(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_ledger_txns.beancount"


@pytest.fixture
def filepath_rx(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_rx.beancount"


@pytest.fixture
def filepath_rx_copy(filepath_rx, temp_dir) -> abc.Iterator[Path]:
    string = shutil.copy(filepath_rx, temp_dir)
    path = Path(string)
    yield path
    path.unlink()


@pytest.fixture
def filepath_no_file(res_dir) -> abc.Iterator[Path]:
    """Filepath to a beancount file which does not exist."""
    filepath = res_dir / "i_do_not_exist.beancount"
    assert not filepath.is_file()
    yield filepath


@pytest.fixture
def filepath_empty_txt_file(res_dir) -> abc.Iterator[Path]:
    """Filepath to an empty text file."""
    filepath = res_dir / "empty_txt_file.txt"
    assert filepath.is_file()
    with filepath.open("r") as file:
        assert file.read() == ""
    yield filepath


@pytest.fixture
def entries_ledger(filepath_ledger) -> abc.Iterator[data.Entries]:
    entries, errors, options = beancount.loader.load_file(filepath_ledger)
    yield entries


@pytest.fixture
def txns_ledger(filepath_ledger_txns) -> abc.Iterator[list[data.Transaction]]:
    txns, errors, options = beancount.loader.load_file(filepath_ledger_txns)
    yield txns


@pytest.fixture
def txn(txns_ledger) -> abc.Iterator[data.Transaction]:
    yield txns_ledger[0]


@pytest.fixture
def txn_payroll(txns_ledger) -> abc.Iterator[data.Transaction]:
    txn = txns_ledger[19]
    assert txn.payee == "BayBook"
    assert txn.date == datetime.date(2020, 1, 16)
    yield txn


@pytest.fixture
def txns_rx(filepath_rx) -> abc.Iterator[list[data.Transaction]]:
    txns, errors, options = beancount.loader.load_file(filepath_rx)
    yield txns


@pytest.fixture
def txns_rx_copy(filepath_rx_copy) -> abc.Iterator[list[data.Transaction]]:
    txns, errors, options = beancount.loader.load_file(filepath_rx_copy)
    yield txns


@pytest.fixture
def rx_txn_chase(txns_rx) -> abc.Iterator[data.Transaction]:
    txn = txns_rx[-1]
    assert txn.payee == "Chase"
    assert txn.date == datetime.date(2022, 10, 31)
    yield txn


@pytest.fixture
def filepath_rx_content(filepath_rx, encoding) -> abc.Iterator[str]:
    yield filepath_rx.read_text(encoding)


@pytest.fixture
def txns_rx_content(filepath_rx_content, encoding) -> abc.Iterator[str]:
    """Content of txns_rx relating to transactions"""
    contents_rx_lines = filepath_rx_content.split("\n")
    yield "\n".join(contents_rx_lines[6:-3])


@pytest.fixture
def tag_x() -> abc.Iterator[str]:
    yield "x_txn"


@pytest.fixture
def tag_rx() -> abc.Iterator[str]:
    yield "rx_txn"
