"""Tests for `config` module."""

import sys

import pytest

from beanahead import config as m

from .conftest import also_get_stdout, also_get_stderr

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


def test_default_options_values(account_root_names_dflt):
    """Verify default options values.

    Also verifies value of constants.
    """
    assert m._print_stdout is True

    assert m._account_root_names == account_root_names_dflt
    assert m.DEFAULT_ACCOUNT_ROOT_NAMES == account_root_names_dflt


def test_print_stream():
    """Tests output of print stream between stdout and stderr."""
    assert m.get_print_file() is sys.stdout

    def print_something():
        print("something", file=m.get_print_file())

    _, prnt = also_get_stdout(print_something)
    assert prnt == "something\n"
    _, prnt = also_get_stderr(print_something)
    assert not prnt

    m.set_print_stderr()
    _, prnt = also_get_stdout(print_something)
    assert not prnt
    _, prnt = also_get_stderr(print_something)
    assert prnt == "something\n"

    m.set_print_stdout()
    _, prnt = also_get_stdout(print_something)
    assert prnt == "something\n"
    _, prnt = also_get_stderr(print_something)
    assert not prnt


def test_account_name_roots(account_root_names_dflt):
    """Tests methods for getting and setting account name roots."""
    rtrn_dflt = m.get_account_root_names()
    assert rtrn_dflt == account_root_names_dflt

    names = {"name_assets": "Biens", "name_invalid": "Irrelevant"}
    with pytest.raises(ValueError, match="'names' parameter can only contain keys:"):
        m.set_account_root_names(names)
    assert m.get_account_root_names() == account_root_names_dflt  # verify all unchnaged

    names = {"name_assets": "Biens", "name_income": "Ingresos"}
    set_names = m.set_account_root_names(names)
    assert set_names == account_root_names_dflt | names

    reset_names = m.reset_account_root_names()
    assert reset_names == account_root_names_dflt == m.get_account_root_names()
