"""Tests for `config` module."""

import sys

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


def test_print_stream():
    """Tests output of print stream between stdout and stderr."""
    assert m._print_stdout is True
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
