"""Tests for defined plugins."""

import copy
import datetime
from decimal import Decimal

from beanahead.plugins import rx_txn_plugin as m

from .conftest import get_entries_from_string

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


def test_convert_meta():
    input_ = """
        2022-10-01 open Assets:US:BofA:Checking

        2022-10-01 * "Payee" ""
          Assets:US:BofA:Checking                  -52.44 USD

        2022-10-02 balance Assets:US:BofA:Checking   -52.44 USD

        2022-10-03 * "Metro" "Tram tickets, Metro Authority" #rx_txn
          freq: "SMS"
          Assets:US:BofA:Checking    -40.00 USD
          Expenses:Transport:Tram

        2022-10-05 * "Account Fee" "Monthly bank fee" #rx_txn
          freq: "BMS"
          roll: FALSE
          Assets:US:BofA:Checking  -4.00 USD
          Expenses:Financial:Fees

        2022-10-07 * "EDISON" "Electricity, monthly fixed tarrif" #rx_txn
          freq: "m"
          final: 2023-07-05
          other_meta: "Edison other meta value"
          Assets:US:BofA:Checking    -65.00 USD
          Expenses:Home:Electricity
    """
    entries = get_entries_from_string(input_)
    assert len(entries) == 6
    orig_entries = copy.deepcopy(entries)

    rtrn_entries, options = m.convert_meta(entries, {})
    assert options == []

    # verify non-transactions returned unchanged
    for i in range(3):
        assert orig_entries[i] == rtrn_entries[i]

    def make_assertion(i: int, meta: dict):
        assert rtrn_entries[i] == orig_entries[i]._replace(meta=meta)

    meta = {
        "filename": "<string>",
        "lineno": 9,
        "freq": "SMS",
        "__tolerances__": {"USD": Decimal("0.005")},
        "final": None,
        "roll": True,
    }
    make_assertion(3, meta)

    meta = {
        "filename": "<string>",
        "lineno": 14,
        "freq": "BMS",
        "roll": False,
        "__tolerances__": {"USD": Decimal("0.005")},
        "final": None,
    }
    make_assertion(4, meta)

    meta = {
        "filename": "<string>",
        "lineno": 20,
        "freq": "m",
        "final": datetime.date(2023, 7, 5),
        "other_meta": "Edison other meta value",
        "__tolerances__": {"USD": Decimal("0.005")},
        "roll": True,
    }
    make_assertion(5, meta)
