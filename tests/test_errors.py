"""Tests for `errors` module."""

from collections import abc
from pathlib import Path

import pytest

from beanahead import errors as m

# pylint: disable=missing-function-docstring, missing-type-doc, missing-class-docstring
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


@pytest.fixture
def path() -> abc.Iterator[Path]:
    yield Path("dummy/path/to/ledger.beancount")


def test_errors_reliant_on_subclass_message():
    assert isinstance(m.BeancountFileExistsError(), FileExistsError)
    assert isinstance(m.BeanaheadFileExistsError(), FileExistsError)
    assert isinstance(m.BeanaheadFileKeyError(), Exception)
    assert isinstance(m.RegularTransactionsDefinitionError(), Exception)


def test_BeanaheadLedgerFileExistsError(path):
    error = m.BeanaheadLedgerFileExistsError(path)
    assert isinstance(error, FileExistsError)
    expected = (
        f"'{path}' does not represent a beanahead Expected Transactions"
        " Ledger file. NB The path does represent another beanahead file."
        " Might you have passed a Regular Expected Transactions Definitions"
        " file by mistake?"
    )
    assert str(error) == expected


def test_BeancountFileExistsError(path):
    errors_ = [m.BeancountFileExistsError(), m.BeanaheadFileExistsError()]
    error = m.BeancountLoaderErrors(path, errors_)
    assert isinstance(error, Exception)
    expected = (
        "The following errors were raised when attempting to load ledger from"
        f" {path}:\n[BeancountFileExistsError(), BeanaheadFileExistsError()]."
    )
    assert str(error) == expected


def test_BeanaheadWriteError(path):
    reverted = [
        Path("./reverted/path/x.beancount"),
        Path("./reverted/path/rx.beancount"),
    ]
    error = m.BeanaheadWriteError(path, reverted, overwrite=True)
    assert isinstance(error, Exception)

    expected = (
        f"An error occurred when attempting to overwrite '{path}'."
        " The following files have been reverted to their most recent saved content:"
        "\nreverted\\path\\x.beancount"
        "\nreverted\\path\\rx.beancount"
    )
    assert str(error) == expected

    # verify effet of alternative arguments
    error = m.BeanaheadWriteError(path, reverted=None, overwrite=False)
    expected = f"An error occurred when attempting to write to '{path}'."
    assert str(error) == expected
