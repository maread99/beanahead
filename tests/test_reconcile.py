"""Tests for `reconcile` module."""

from collections import abc
import contextlib
import copy
import datetime
from decimal import Decimal
import io
import itertools
from pathlib import Path
import re
import textwrap
from types import GeneratorType

import beancount
from beancount.core import data
import pytest

from beanahead import reconcile as m
from beanahead.scripts import cli

from . import cmn
from .conftest import get_entries_from_string, set_cl_args

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
def extraction_txns(filepath_recon_extraction) -> abc.Iterator[list[data.Transaction]]:
    txns, _, _ = beancount.loader.load_file(filepath_recon_extraction)
    yield txns


@pytest.fixture
def txn_burger_bar_223010(extraction_txns) -> abc.Iterator[list[data.Transaction]]:
    txn = extraction_txns[21]
    assert txn.payee == "25 Degrees Burger Bar"
    assert txn.date == datetime.date(2022, 10, 30)
    yield txn


@pytest.fixture
def test_txns() -> abc.Iterator[list[data.Transaction]]:
    string = """
        2022-10-03 * "Account Fee" ""
          Assets:US:BofA:Checking  -4.00 USD
          Expenses:Financial:Fees

        2022-10-05 * "Edison Power green tariff" ""
          Assets:US:BofA:Checking    -65.22 USD
          Expenses:Home:Electricity

        2022-10-07 * "Edison Power Battery pack" ""
          Liabilities:US:Chase:Slate  -175.00 USD
          Expenses:Home:Electricty

        2022-10-07 * "Metro" "Tram tickets, Metro Authority"
          Liabilities:US:Chase:Slate  -120.00 USD
          Expenses:Transport:Tram

        2022-10-10 * "Slate" "Credit Card payment"
          Assets:US:BofA:Checking     -250.00 USD
          Liabilities:US:Chase:Slate

        2022-10-11 * "Baybook" ""
          Assets:US:BofA:Checking   -2000 USD
          Income:Salary:Baybook

        2022-10-25 * "Baybook" ""
          Assets:US:Vanguard   400 USD
          Income:Salary:Baybook
        """
    yield get_entries_from_string(string)


def test_load_extraction_file(filepath_recon_extraction):
    """Also tests `separate_out_txns`."""
    filepath = filepath_recon_extraction
    extracted_entries = m.load_extraction_file(filepath)
    expected_txns, errors, _ = beancount.loader.load_file(filepath)
    assert errors

    # verify that the txns are the same
    cmn.assert_txns_equal(extracted_entries[:-2], expected_txns)
    # and that entries loaded via 'load_extraction_file' will include bal entries...

    def assert_bal_boa(bal: data.Balance):
        assert bal.date == datetime.date(2022, 11, 1)
        assert bal.account == "Assets:US:BofA:Checking"
        assert bal.amount == data.Amount(Decimal("5320.22"), "USD")

    def assert_bal_slate(bal: data.Balance):
        assert bal.date == datetime.date(2022, 11, 1)
        assert bal.account == "Liabilities:US:Chase:Slate"
        assert bal.amount == data.Amount(Decimal("-520.33"), "USD")

    assert_bal_boa(extracted_entries[-2])
    assert_bal_slate(extracted_entries[-1])

    # test `separate_out_txns`
    extracted_txns, extracted_bals = m.separate_out_txns(extracted_entries)
    cmn.assert_txns_equal(extracted_txns, expected_txns)
    assert_bal_boa(extracted_bals[0])
    assert_bal_slate(extracted_bals[1])


def test_get_close_txns(extraction_txns, txn_burger_bar_223010):
    f = m.get_close_txns
    txns = extraction_txns
    txn = txn_burger_bar_223010
    txn_date = datetime.date(2022, 10, 30)

    rtrn = f(txns, txn, datetime.timedelta(0))
    assert rtrn == txns[21:23]
    assert txns[20].date < txn_date
    assert txns[21].date == txn_date
    assert txns[22].date == txn_date
    assert txns[23].date > txn_date

    rtrn = f(txns, txn, datetime.timedelta(1))
    assert rtrn == txns[-6:]
    assert txns[-6].date == datetime.date(2022, 10, 29)
    assert txns[-7].date < txns[-6].date
    assert txns[-1].date == datetime.date(2022, 10, 31)

    # no additional txns within delta...
    for i in range(2, 5):
        assert rtrn == f(txns, txn, datetime.timedelta(i))

    # until...
    rtrn = f(txns, txn, datetime.timedelta(5))
    assert rtrn == txns[-8:]
    assert txns[-8].date == datetime.date(2022, 10, 25)
    assert txns[-9].date < datetime.date(2022, 10, 25)


def test_bal_sheet_accounts_match(test_txns):
    """Also tests `get_accounts_matches` and `get_basic_matches`."""
    txns = test_txns
    f = m.bal_sheet_accounts_match
    matches = (
        (0, 1, 4, 5),
        (0, 1, 4, 5),
        (2, 3, 4),
        (2, 3, 4),
        (0, 1, 2, 3, 4, 5),
        (0, 1, 4, 5),
        (6,),
    )

    for matches_, txn in zip(matches, txns):
        for i, txn_ in enumerate(txns):
            match = f(txn, txn_)
            assert match if i in matches_ else not match

    f = m.get_accounts_matches
    for txn, matches_ in zip(txns, matches):
        assert f(txns, txn) == [txns[i] for i in matches_]

    txn = txns.pop(1)
    f = m.get_basic_matches
    # should just match "Account Fee" and "Slate"
    assert f(txns, txn) == [txns[i] for i in (0, 3)]


def test_get_payee_matches(test_txns):
    """Also tests `get_pattern`."""
    txn = test_txns[1]
    regex_compiled = m.get_pattern(txn)
    assert regex_compiled.pattern == "^.*(?=Edison|Power|green|tariff).*$"
    assert m.get_payee_matches(test_txns, txn) == [txn, test_txns[2]]


def test_get_common_accounts():
    """Also tests `get_common_balance_sheet_accounts` and `get_amount_for_account`."""
    test_input = """
        2022-10-03 * "A" ""
          Assets:US:BofA:Checking  -1.00 USD
          Expenses:Financial:Fees

        2022-10-05 * "B" ""
          Assets:US:BofA:Checking    -11.00 USD
          Expenses:Home:Electricity

        2022-10-07 * "C" ""
          Assets:US:BofA:Checking                      1350.60 USD
          Assets:US:Vanguard:Cash                      1200.00 USD
          Income:US:BayBook:Salary                    -4615.38 USD
          Income:US:BayBook:GroupTermLife               -24.32 USD
          Expenses:Health:Life:GroupTermLife             24.32 USD
          Expenses:Health:Dental:Insurance                2.90 USD
          Expenses:Home:Electricity
          Assets:US:Federal:PreTax401k                -1200.00 IRAUSD
          Expenses:Taxes:Y2020:US:Federal:PreTax401k   1200.00 IRAUSD
          Assets:US:BayBook:Vacation                         5 VACHR
          Income:US:BayBook:Vacation                        -5 VACHR

        2022-10-09 * "D" ""
          Assets:US:BofA:Checking                      1350.60 USD
          Income:US:BayBook:Salary                    -4615.38 USD
          Income:US:BayBook:GroupTermLife               -24.32 USD
          Liabilities:US:Chase:Slate  -120.00 USD
          Expenses:Home:Electricity                     321.33 USD
          Assets:US:Federal:PreTax401k                -1200.00 IRAUSD
          Income:US:BayBook:Vacation                        -5 VACHR
          Expenses:Transport:Tram

        2022-10-11 * "E" ""
          Assets:US:BofA:Checking    -65.00 USD
          Expenses:Home:Electricity

        2022-10-12 * "F" ""
          Assets:US:Vanguard:Cash    65.00 USD
          Expenses:Health:Life:GroupTermLife
        """
    f = m.get_common_accounts
    a, b, c, d, e, f_ = get_entries_from_string(test_input)
    assert f(a, b) == {"Assets:US:BofA:Checking"}
    expected = {
        "Assets:US:BofA:Checking",
        "Income:US:BayBook:Salary",
        "Income:US:BayBook:GroupTermLife",
        "Expenses:Home:Electricity",
        "Assets:US:Federal:PreTax401k",
        "Income:US:BayBook:Vacation",
    }
    assert f(c, d) == expected
    assert f(e, f_) == set()

    f2 = m.get_common_balance_sheet_accounts
    assert f2(a, b) == {"Assets:US:BofA:Checking"}
    expected = {"Assets:US:BofA:Checking", "Assets:US:Federal:PreTax401k"}
    assert f2(c, d) == expected
    assert f2(e, f_) == set()

    f3 = m.get_amount_for_account
    assert f3(c, "Income:US:BayBook:Salary") == data.Amount(Decimal("-4615.38"), "USD")
    assert f3(c, "Assets:US:BayBook:Vacation") == data.Amount(Decimal("5"), "VACHR")


def test_get_posting_to_account():
    test_input = """
        2022-10-05 * "The payee" ""
          Assets:US:BofA:Checking    -11.00 USD
          Assets:US:BofA:Checking    -22.00 USD
          Expenses:Home:Electricity
        """
    f = m.get_posting_to_account
    txn = get_entries_from_string(test_input)[0]
    expected = (
        "Posting(account='Expenses:Home:Electricity', units=33.00 USD, cost=None,"
        " price=None, flag=None, meta={'filename': '<string>', 'lineno': 5,"
        " '__automatic__': True})"
    )
    rtrn = f(txn, "Expenses:Home:Electricity")
    assert str(rtrn) == expected
    assert f(txn, "Expenses:Not:An:Account") is None
    account = "Assets:US:BofA:Checking"
    match = re.escape(
        "Transaction cannot have multiple postings to the same account"
        " although the following transaction has multiple postings to"
        f" '{account}':\n{txn}"
    )
    with pytest.raises(ValueError, match=match):
        f(txn, account)


class TestNumberAndSort:
    @pytest.fixture
    def txns(self) -> abc.Iterator[list[data.Transaction]]:
        yield get_entries_from_string(
            """
            2022-10-03 * "A" ""
              Assets:US:BofA:Checking                      10 USD
              Assets:US:Vanguard:Cash                      8 USD
              Income:US:BayBook:Salary                    -20 USD
              Income:US:BayBook:GroupTermLife             -1 USD
              Expenses:Health:Life:GroupTermLife           1 USD
              Expenses:Health:Dental:Insurance

            2022-10-04 * "B" "No common account with A"
              Liabilities:US:Chase:Slate  -10 USD
              Expenses:Home:Electricity

            2022-10-05 * "C" "Common accounts with A but different currency"
              Assets:US:BofA:Checking     10 EUR
              Income:US:BayBook:Salary

            2022-10-06 * "D" "Common accounts with A but different sign"
              Assets:US:BofA:Checking     -10 USD
              Income:US:BayBook:Salary

            2022-10-08 * "E" "One common account with A, same value"
              Assets:US:BofA:Checking      10 USD
              Expenses:Home:Electricity

            2022-10-08 * "F" "Multiple common accounts with A, same value"
              Assets:US:BofA:Checking                      10 USD
              Assets:US:Vanguard:Cash                       8 USD
              Income:US:BayBook:Salary                    -20 USD
              Income:US:BayBook:GroupTermLife              -1 USD
              Expenses:Home:Electricity

            2022-10-09 * "G" "One common account with A, half value"
              Assets:US:BofA:Checking      5 USD
              Expenses:Home:Electricity

            2022-10-10 * "H" "One common account with A, double value"
              Assets:US:BofA:Checking      20 USD
              Expenses:Home:Electricity

            2022-10-12 * "I" "Multiple common accounts with A, same diff"
              ; date sorts before b as more common accounts
              Assets:US:BofA:Checking                       5 USD
              Assets:US:Vanguard:Cash                       4 USD
              Income:US:BayBook:Salary                    -20 USD   ; not bal sheet acc
              Expenses:Home:Electricity

            2022-10-12 * "J" "Multiple common accounts with A, various diff"
              ; date sorts before b and i as more common accounts
              Assets:US:BofA:Checking                      20 USD  ; double 0.5
              Assets:US:Vanguard:Cash                      6 USD  ; 3/4 0.25
              Income:US:BayBook:Salary                    -20 USD ; same value not bal
              Income:US:BayBook:GroupTermLife             -2 USD ; double 0.5 not bal
              Expenses:Home:Electricity

            2022-10-13 * "K" "Multiple common accounts with A, one diff sign"
              Assets:US:BofA:Checking                      -5 USD
              Assets:US:Vanguard:Cash                       4 USD
              Income:US:BayBook:Salary                    -40 USD
              Expenses:Home:Electricity

            2022-10-15 * "L" "As A"
              Assets:US:BofA:Checking                      10 USD
              Assets:US:Vanguard:Cash                      8 USD
              Income:US:BayBook:Salary                    -20 USD
              Income:US:BayBook:GroupTermLife             -1 USD
              Expenses:Health:Life:GroupTermLife           1 USD
              Expenses:Health:Dental:Insurance
            """
        )

    def test_number_diff(self, txns):
        (a, b, c, d, e, f_, g, h, i, j, k, l) = txns
        f = m.number_diff
        assert f(a, b) == Decimal("1")
        assert f(a, c) == Decimal("1")
        assert f(a, d) == Decimal("1")
        assert f(a, e) == Decimal("0")
        assert f(a, f_) == Decimal("0")
        assert f(a, g) == Decimal("0.5")
        assert f(a, h) == Decimal("0.5")
        assert f(a, i) == Decimal("0.5")
        assert f(a, j) == Decimal("0.375")
        assert f(a, k) == Decimal("1")
        assert f(a, l) == Decimal("0")

    def test_have_same_number(self, txns):
        (a, b, c, d, e, f_, g, h, i, j, k, l) = txns
        expected = (
            (a, e),
            (a, f_),
            (a, l),
            (e, f_),
            (e, l),
            (f_, l),
            (g, i),
            (h, j),
        )
        for txn_y, txn_z in itertools.combinations(txns, 2):
            rtrn = m.have_same_number(txn_y, txn_z)
            assert rtrn if (txn_y, txn_z) in expected else not rtrn

    def test_get_number_matches(self, txns):
        f = m.get_number_matches
        (a, b, c, d, e, f_, g, h, i, j, k, l) = txns

        # verify for 'exact' only
        # also check exact by default...
        assert f(txns, a) == f(txns, a, Decimal(0)) == f(txns, l) == [a, e, f_, l]
        assert f(txns, e) == [a, e, f_, l]
        assert f(txns, f_) == [a, e, f_, l]
        # following should only match with themselves
        assert f(txns, g) == f(txns, i) == [g, i]
        assert f(txns, h) == f(txns, j) == [h, j]

        for txn in [b, c, d, k]:
            assert f(txns, txn) == [txn]

        # verify margin
        assert f(txns, a, Decimal(0.374)) == [a, e, f_, l]
        expected = [a, e, f_, j, l]
        assert f(txns, a, Decimal(0.375)) == f(txns, a, Decimal(0.499)) == expected

        expected = [a, e, f_, g, h, i, j, l]
        assert f(txns, a, Decimal(0.5)) == f(txns, a, Decimal(0.99)) == expected
        assert f(txns, a, Decimal(1)) == txns

    def test_sort_by_number(self, txns):
        (a, b, c, d, e, f_, g, h, i, j, k, l) = txns
        sorted_txns = m.sort_by_number(txns[1:], txns[0])
        assert sorted_txns == [e, f_, l, j, g, h, i, b, c, d, k]

    def test_sort_by_date(self, txns):
        (a, b, c, d, e, f_, g, h, i, j, k, l) = txns
        f_ = txns.pop(5)
        sorted_txns = m.sort_by_date(txns, f_)
        assert sorted_txns == [e, g, d, h, c, j, i, b, a, k, l]


class TestGetMatches:
    """Tests for `get_matches`."""

    @pytest.fixture
    def txn(self) -> abc.Iterator[data.Transaction]:
        """Transaction to match."""
        input_ = """
            2022-10-06 * "0" "Txn to match"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol
            """
        yield get_entries_from_string(input_)[0]

    @pytest.fixture
    def txns_one_payee_match(self) -> abc.Iterator[list[data.Transaction]]:
        """Only txn[2] matches on payee."""
        input_ = """
            2022-09-30 * "A" "No match as left of left date limit"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-01 * "B" "Matches on left extreme of viable dates"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-06 * "0" "I do match on payee!"
              Assets:US:BofA:Checking                     -20 USD

            2022-10-06 * "C" "No match as no common balance sheet account"
              Liabilities:US:Chase:Slate                  -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "D" "Matches on right extreme of viable dates"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "E" "Match on upper side of 2% limit"
              Assets:US:BofA:Checking                  -51.02 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "F" "Match on lower side of 2% limit"
              Assets:US:BofA:Checking                     -49 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "G" "No Match as above upper side of 2% limit"
              Assets:US:BofA:Checking                  -51.03 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "H" "No Match as under lower side of 2% limit"
              Assets:US:BofA:Checking                  -48.99 USD
              Expenses:Food:Restaurant                     30 USD
              Expenses:Food:Alcohol

            2022-10-12 * "I" "No match as right of right date limit"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol
          """
        yield get_entries_from_string(input_)

    def test_only_one_payee_match(self, txn, txns_one_payee_match):
        txns = txns_one_payee_match
        # verify that when only one payee match, matches that and nothing else
        assert m.get_matches(txns, txn) == [txns[2]]

    @pytest.fixture
    def txns_no_payee_match(
        self, txns_one_payee_match
    ) -> abc.Iterator[list[data.Transaction]]:
        txns = txns_one_payee_match
        txns.pop(2)
        yield txns

    def test_txns_no_payee_match(self, txn, txns_no_payee_match):
        a, b, c, d, e, f_, g, h, i = txns_no_payee_match
        assert m.get_matches(txns_no_payee_match, txn) == [b, d, e, f_]

    def test_mult_payee_match(self, txn):
        input_ = """
            2022-09-30 * "0" "A. No match as left of left date limit"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-01 * "0" "B. Matches on left extreme of viable dates"
              Assets:US:BofA:Checking                  -50.01 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-05 * "0" "C. Matches on day before, exact value"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-06 * "X" "D. I do NOT match on payee!"
              Assets:US:BofA:Checking                     -50 USD

            2022-10-06 * "0" "E. No match as no common balance sheet account"
              Liabilities:US:Chase:Slate                  -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-06 * "0" "F. Exact match"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-07 * "0" "G. Matches on day after, exact value"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "0" "H. Matches on right extreme of viable dates"
              Assets:US:BofA:Checking                  -50.01 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "0" "I. Match on upper side of 2% limit"
              Assets:US:BofA:Checking                  -51.02 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "0" "J. Match on lower side of 2% limit"
              Assets:US:BofA:Checking                     -49 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "0" "K. Above upper side of 2% limit"
              Assets:US:BofA:Checking                     -70 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-11 * "0" "L. Under lower side of 2% limit"
              Assets:US:BofA:Checking                     -20 USD
              Expenses:Food:Restaurant                     30 USD
              Expenses:Food:Alcohol

            2022-10-12 * "0" "M. No match as right of right date limit"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol
          """
        a, b, c, d, e, f_, g, h, i, j, k, l, m_ = txns = get_entries_from_string(input_)
        f = m.get_matches
        assert f(txns, txn) == [f_]
        txns.remove(f_)  # remove exact match

        # verify returns only exact equally close matches
        assert f(txns, txn) == [c, g]

        # remove those exact equally close matches
        txns.remove(c)
        txns.remove(g)

        # verify returns all remaining matches, but only those considered to match
        assert f(txns, txn) == [b, h, i, j, k, l]


class TestUserInput:
    """Tests for functions that request user input."""

    @pytest.fixture
    def txn(self) -> abc.Iterator[data.Transaction]:
        """Transaction to match."""
        input_ = """
            2022-10-06 * "X" "Transaction to match"
              Assets:US:BofA:Checking   -50 USD
              Expenses:Food:Restaurant   40 USD
              Expenses:Food:Alcohol
            """
        yield get_entries_from_string(input_)[0]

    @pytest.fixture
    def txn2(self) -> abc.Iterator[data.Transaction]:
        """Another transaction to match."""
        input_ = """
            2022-10-26 * "X2" "Another transaction to match"
              Assets:US:BofA:Checking   -222 USD
              Expenses:Food:Restaurant   200 USD
              Expenses:Food:Alcohol
            """
        yield get_entries_from_string(input_)[0]

    @pytest.fixture
    def txns(self) -> abc.Iterator[list[data.Transaction]]:
        input_ = """
            2022-10-03 * "A" ""
              Assets:US:BofA:Checking   -50 USD
              Expenses:Food:Restaurant   40 USD
              Expenses:Food:Alcohol

            2022-10-07 * "B" ""
              Assets:US:BofA:Checking   -51 USD

            2022-10-26 * "C" ""
              Assets:US:BofA:Checking  -222 USD
              Expenses:Food:Restaurant  200 USD
              Expenses:Food:Alcohol
          """
        yield get_entries_from_string(input_)

    def test_confirm_single(self, mock_input, txn, txns):
        f = m.confirm_single
        expected_print = textwrap.dedent(
            """
            ---
            Expected Transaction:
            2022-10-06 * "X" "Transaction to match"
              Assets:US:BofA:Checking   -50 USD
              Expenses:Food:Restaurant   40 USD
              Expenses:Food:Alcohol

            Incoming Transaction:
            2022-10-07 * "B" ""
              Assets:US:BofA:Checking  -51 USD

            Do you want to match the above transactions? y/n: """
        )
        expected_print = expected_print[1:] + "\n"

        # verify confirmed match
        inputs = (v for v in ("y",))
        mock_input(inputs)
        output = io.StringIO()
        poss_match = txns[1]
        with contextlib.redirect_stdout(output):
            rtrn = f(txn, [poss_match])
        assert output.getvalue().endswith(expected_print)
        assert rtrn is poss_match

        # verify non-confirmed match
        inputs = (v for v in ("n",))
        mock_input(inputs)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rtrn = f(txn, [poss_match])
        assert output.getvalue().endswith(expected_print)
        assert rtrn is None

        # verify invalid input
        expected_print += "3 is not valid input, please try again, y/n: \n"
        inputs = (v for v in ("3", "y"))
        mock_input(inputs)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rtrn = f(txn, [poss_match])
        assert output.getvalue().endswith(expected_print)
        assert rtrn is poss_match

        # verify multiple invalid input
        inputs = (v for v in ("3", "spam", "no", "y"))
        mock_input(inputs)
        assert f(txn, [poss_match]) is poss_match

    def test_get_mult_match(self, mock_input, txn, txns):
        f = m.get_mult_match
        expected_print = textwrap.dedent(
            """
            ---
            Expected Transaction:
            2022-10-06 * "X" "Transaction to match"
              Assets:US:BofA:Checking   -50 USD
              Expenses:Food:Restaurant   40 USD
              Expenses:Food:Alcohol


            Incoming Transactions:

            0
            2022-10-03 * "A" ""
              Assets:US:BofA:Checking   -50 USD
              Expenses:Food:Restaurant   40 USD
              Expenses:Food:Alcohol

            1
            2022-10-07 * "B" ""
              Assets:US:BofA:Checking  -51 USD

            """
        )
        expected_print += (
            "Which of the above incoming transactions do you wish to match with the"
            " expected transaction, or 'n' for None, [0-1]/n:\n"
        )
        expected_print = expected_print[1:]
        txns = txns[:2]

        # verify confirmed matches
        for i in (0, 1):
            inputs = (v for v in (str(i),))
            mock_input(inputs)
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                rtrn = f(txn, txns)
            assert output.getvalue().endswith(expected_print)
            assert rtrn is txns[i]

        # verify non-confirmed match
        inputs = (v for v in ("n",))
        mock_input(inputs)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rtrn = f(txn, txns)
        assert output.getvalue().endswith(expected_print)
        assert rtrn is None

        # verify invalid input
        expected_print += "2 is not valid input, please try again [0-1]/n: \n"
        inputs = (v for v in ("2", "0"))
        mock_input(inputs)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            rtrn = f(txn, txns)
        assert output.getvalue().endswith(expected_print)
        assert rtrn is txns[0]

        # verify multiple invalid input
        inputs = (v for v in ("2", "3", "spam", "no", "1"))
        mock_input(inputs)
        assert f(txn, txns) is txns[1]

    def test_reconcile_x_txns(self, mock_input, txn, txn2, txns):
        f = m.reconcile_x_txns
        x_txns = [txn, txn2]

        # verify each option where mult options
        # txns[1] is dated 07 is closer and so appears as option 0, txn[0] is option 1
        for i, i_ in zip((0, 1), (1, 0)):
            inputs = (v for v in (str(i), "y"))
            mock_input(inputs)
            rtrn = f(x_txns, txns)
            assert rtrn == [
                (txn, txns[i_]),
                (txn2, txns[-1]),
            ]

        # verify doesn't reconcile where user response is "n"
        inputs = (v for v in ("n", "y"))
        mock_input(inputs)
        rtrn = f(x_txns, txns)
        assert rtrn == [(txn2, txns[-1])]

        for i, i_ in zip((0, 1), (1, 0)):
            inputs = (v for v in (str(i), "n"))
            mock_input(inputs)
            rtrn = f(x_txns, txns)
            assert rtrn == [(txn, txns[i_])]

        inputs = (v for v in ("n", "n"))
        mock_input(inputs)
        rtrn = f(x_txns, txns)
        assert rtrn == []

        # verify returns as expected with invalid inputs
        inputs = (v for v in ("spam", "2", "11", "0", "ham", "y"))
        mock_input(inputs)
        rtrn = f(x_txns, txns)
        assert rtrn == [
            (txn, txns[1]),
            (txn2, txns[-1]),
        ]


class TestUpdateNewTxn:
    """Tests for `update_new_txn` function"""

    @pytest.fixture
    def new_txns(self) -> abc.Iterator[list[data.Transaction]]:
        """New Transactions.

        The first two transactions correspond with an expected transaction
        at the same index of `x_txns`.

        [0] represents a minimal definition.

        [1] represents a definition with additional information.

        [2] and [3] represent further new transactions for which no
        corresponding expected transactions are defined.
        """
        input_ = textwrap.dedent(
            """
            2022-10-08 * "new payee" ""
              Assets:US:BofA:Checking                  -52.44 USD

            2022-10-18 * "new payee" "new_txn narration" #new_tag
              new: "New meta value"
              dup: "I rule"
              Assets:US:BofA:Checking                  -52.44 USD
                checking: "I should survive!"
                new_txn_checking: "I should be there too!"
              Expenses:Food:Alcohol                     20.00 USD
                new_alc: "New alc meta value"
                dup_alc: "I take precedence"

            2022-10-24 * "Another Txn" "Not matched to an x_txn"
              Assets:US:BofA:Checking                  -12.22 USD

            2022-10-26 * "Yet Another Txn" "Not matched to an x_txn"
              Assets:US:BofA:Checking                  -88.88 USD
            """
        )
        yield get_entries_from_string(input_)

    @pytest.fixture
    def x_txns(self) -> abc.Iterator[list[data.Transaction]]:
        """Expected transactions for tests.

        [0] and [1] correspond with a new transaction at the same index of
        `new_txns`.
        [2] and [3] do not correspond with any defined new transaction.
        """
        input_ = textwrap.dedent(
            """
            2022-10-06 * "x_txn payee" "x_txn narration"  #x_txn #other_tag
              freq: "2w"
              roll: FALSE
              final: 2023-02-23
              other_meta: "Other meta value"
              Assets:US:BofA:Checking                     -50 USD
              Expenses:Food:Restaurant                     40 USD
              Expenses:Food:Alcohol

            2022-10-16 * "x_txn payee" "x_txn narration"  #x_txn #x_txn_tag
              freq: "2w"
              roll: FALSE
              final: 2023-02-23
              x_txn: "X meta value"
              dup: "I won't make it"
              Assets:US:BofA:Checking                     -50 USD
                checking: "I should be overwritten"
                x_txn_checking: "I should be carried over"
              Expenses:Food:Restaurant                     40 USD
                x_txn_expenses: "I should survive"
              Expenses:Food:Alcohol
                x_txn_alc: "X alc meta value"
                dup_alc: "but not me!"

            2022-10-20 * "Extra x-txn" "Not matched to an new_txn"
              Assets:US:Liabilities:Chase                  -123.45 USD

            2022-10-22 * "Another Extra x-txn" "Not matched to an new_txn"
              Assets:US:Liabilities:Chase                  -453.21 USD
            """
        )
        yield get_entries_from_string(input_)

    @pytest.fixture
    def txns_minimal(self, x_txns, new_txns) -> abc.Iterator[list[data.Transaction]]:
        """new_txn representing minimal definition and corresponding x txn."""
        yield x_txns[0], new_txns[0]

    @pytest.fixture
    def txns_additional(self, x_txns, new_txns) -> abc.Iterator[list[data.Transaction]]:
        """new_txn defined with additional info and corresponding x txn."""
        yield x_txns[1], new_txns[1]

    def assert_cost_price_flag_none(self, post: data.Posting):
        assert post.cost is None
        assert post.price is None
        assert post.flag is None

    def assert_minimal_new_txn(self, txn, x_txn, new_txn):
        """Assert `txn` represents the updated minimal definition.

        Asserts that `txn` is `new_txn` updated for `x_txn`, where
        `new_txn` represents the minimal definition and `x_txn` the
        corresponding expected transaction.
        """
        assert txn.date == new_txn.date == datetime.date(2022, 10, 8)
        assert txn.narration == x_txn.narration == "x_txn narration"
        assert txn.tags == frozenset(["other_tag"])

        assert len(txn.meta) == 4
        for key in ["filename", "lineno", "__tolerances__"]:
            assert txn.meta[key] == new_txn.meta[key]
        assert txn.meta["other_meta"] == "Other meta value"

        assert len(txn.postings) == 3
        assert txn.postings[0].account == "Assets:US:BofA:Checking"
        assert txn.postings[0] == new_txn.postings[0]

        assert txn.postings[1].account == "Expenses:Food:Restaurant"
        assert txn.postings[1] == x_txn.postings[1]

        alc_posting = txn.postings[2]
        assert alc_posting.account == "Expenses:Food:Alcohol"
        assert alc_posting.units is None
        self.assert_cost_price_flag_none(alc_posting)
        assert len(alc_posting.meta) == 2
        assert all(k in alc_posting.meta for k in ["filename", "lineno"])

    def test_minimal_new_txn(self, txns_minimal):
        """Test where new_txn has a minimal definition."""
        x_txn, new_txn = txns_minimal
        rtrn = m.update_new_txn(new_txn, x_txn)
        self.assert_minimal_new_txn(rtrn, x_txn, new_txn)

    def assert_new_txn_with_additional_info(self, txn, x_txn, new_txn):
        """Assert `txn` represents the new_txn defined with additional information.

        Asserts that `txn` is `new_txn` updated for `x_txn`, where
        `new_txn` represents the new transaction defined with additional information
        and `x_txn` the corresponding expected transaction.
        """
        assert txn.date == new_txn.date == datetime.date(2022, 10, 18)
        assert txn.narration == new_txn.narration == "new_txn narration"
        assert txn.tags == frozenset(["x_txn_tag", "new_tag"])

        assert len(txn.meta) == 6
        for key in ["filename", "lineno", "__tolerances__"]:
            assert txn.meta[key] == new_txn.meta[key]
        assert txn.meta["x_txn"] == "X meta value"
        assert txn.meta["new"] == "New meta value"
        assert txn.meta["dup"] == "I rule"

        assert len(txn.postings) == 3

        checking_post = txn.postings[0]
        assert checking_post.account == "Assets:US:BofA:Checking"
        assert (
            checking_post != new_txn.postings[0]
        )  # check not amending original meta dict
        assert checking_post.units == data.Amount(Decimal("-52.44"), "USD")
        self.assert_cost_price_flag_none(checking_post)
        assert len(checking_post.meta) == 5
        assert all(k in checking_post.meta for k in ["filename", "lineno"])
        assert checking_post.meta["x_txn_checking"] == "I should be carried over"
        assert checking_post.meta["new_txn_checking"] == "I should be there too!"
        assert checking_post.meta["checking"] == "I should survive!"

        rest_posting = txn.postings[1]
        assert rest_posting.account == "Expenses:Food:Restaurant"
        # verify posting carried over as is (as not otherwise defined on new txn)
        assert txn.postings[1] == x_txn.postings[1]

        alc_posting = txn.postings[2]
        assert alc_posting.account == "Expenses:Food:Alcohol"
        # verify original meta not amended...
        assert alc_posting != new_txn.postings[1]
        # verify as new_txn posting except for updated meta...
        assert alc_posting.units == data.Amount(Decimal("20"), "USD")
        self.assert_cost_price_flag_none(alc_posting)
        assert len(alc_posting.meta) == 5
        assert all(k in alc_posting.meta for k in ["filename", "lineno"])
        assert alc_posting.meta["x_txn_alc"] == "X alc meta value"
        assert alc_posting.meta["new_alc"] == "New alc meta value"
        assert alc_posting.meta["dup_alc"] == "I take precedence"

    def test_new_txn_with_additional_info(self, txns_additional):
        """Test for new_txn defined with additional information."""
        x_txn, new_txn = txns_additional
        rtrn = m.update_new_txn(new_txn, x_txn)
        self.assert_new_txn_with_additional_info(rtrn, x_txn, new_txn)

    def test_update_new_txns(self, new_txns, txns_minimal, txns_additional):
        reconciled_x_txns = [txns_minimal, txns_additional]
        original_new_txns = copy.deepcopy(new_txns)
        rtrn = m.update_new_txns(new_txns, reconciled_x_txns)

        # NB `update_new_txns` does not maintain order and position for first two
        # reconciled_x_txns will be reversed...
        rtrn_minimal = rtrn[1]
        assert rtrn_minimal != original_new_txns[0]
        assert rtrn_minimal != original_new_txns[1]
        self.assert_minimal_new_txn(rtrn_minimal, *txns_minimal)
        rtrn_additional = rtrn[0]
        assert rtrn_additional != original_new_txns[0]
        assert rtrn_additional != original_new_txns[1]
        self.assert_new_txn_with_additional_info(rtrn_additional, *txns_additional)

        assert rtrn[2] == original_new_txns[2]
        assert rtrn[3] == original_new_txns[3]

    def test_map_path_to_reconciled_x_txns(self, x_txns, txns_minimal, txns_additional):
        f = m.map_path_to_reconciled_x_txns
        reconciled_x_txns = [txns_minimal, txns_additional]
        path_a, path_b = Path("path/to/a"), Path("path/to/b")

        x_txns_by_path = {
            path_a: x_txns[:2],
            path_b: x_txns[2:],
        }
        rtrn = f(x_txns_by_path, reconciled_x_txns)
        assert rtrn == {path_a: x_txns[:2]}

        x_txns_by_path = {
            path_a: x_txns[2:],
            path_b: x_txns[:2],
        }
        rtrn = f(x_txns_by_path, reconciled_x_txns)
        assert rtrn == {path_b: x_txns[:2]}

        x_txns_by_path = {
            path_a: [x_txns[i] for i in [0, 2]],
            path_b: [x_txns[i] for i in [1, 3]],
        }
        rtrn = f(x_txns_by_path, reconciled_x_txns)
        assert rtrn == {
            path_a: [x_txns[0]],
            path_b: [x_txns[1]],
        }


class TestReconcileNewTxns:
    """Tests for `reconcile_new_txns` function."""

    @pytest.fixture
    def injection_output(self, temp_dir) -> abc.Iterator[Path]:
        filepath = temp_dir / "injection.beancount"
        assert not filepath.is_file()
        yield filepath
        if filepath.is_file():
            filepath.unlink()

    @pytest.fixture
    def expected_injection_content(self, recon_dir, encoding) -> abc.Iterator[str]:
        filepath = recon_dir / "expected_injection.beancount"
        yield filepath.read_text(encoding)

    @pytest.fixture
    def expected_injection_ascending_content(
        self, recon_dir, encoding
    ) -> abc.Iterator[str]:
        filepath = recon_dir / "expected_injection_ascending.beancount"
        yield filepath.read_text(encoding)

    @pytest.fixture
    def expected_x_content(self, recon_dir, encoding) -> abc.Iterator[str]:
        filepath = recon_dir / "expected_x.beancount"
        yield filepath.read_text(encoding)

    @pytest.fixture
    def expected_rx_content(self, recon_dir, encoding) -> abc.Iterator[str]:
        filepath = recon_dir / "expected_rx.beancount"
        yield filepath.read_text(encoding)

    @pytest.fixture
    def input_responses(self) -> abc.Iterator[GeneratorType]:
        responses = ["y"] * 14 + ["0", "2", "0"] + ["y"]
        yield (v for v in responses)

    def assert_expected_injection(
        self,
        injection: Path,
        expected_injection_content: str,
        txns_extraction,
        encoding: str,
    ):
        injection_content = injection.read_text(encoding)
        assert injection_content == expected_injection_content

        txns_injection, _, _ = beancount.loader.load_file(injection)
        assert len(txns_extraction) == len(txns_injection)

        for txn in txns_injection:
            tid = txn.meta["tid"]
            if "matches" in txn.meta:
                matches = txn.meta["matches"].replace(" ", "").split(",")
                assert tid in matches

    def get_expected_print(
        self,
        num_removals_frm_rx,
        num_removals_frm_x,
        x_path,
        rx_path,
        injection_path,
    ) -> str:
        num_removals = num_removals_frm_rx + num_removals_frm_x
        return textwrap.dedent(
            rf"""
            {num_removals} incoming transactions have been reconciled against expected transactions.
            Updated transactions have been output to '{injection_path}'.
            {num_removals_frm_rx} transactions have been removed from ledger {rx_path}.
            {num_removals_frm_x} transactions have been removed from ledger {x_path}.
            """
        )

    def test_default(
        self,
        filepaths_recon_copy,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_content,
        expected_x_content,
        expected_rx_content,
    ):
        """Test for default options."""
        f = m.reconcile_new_txns
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        ledgers = [str(filepath) for filepath in (rx_path, x_path)]

        mock_input(input_responses)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            f(str(extraction), ledgers)

        expected_print = self.get_expected_print(12, 6, x_path, rx_path, extraction)
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            extraction, expected_injection_content, extraction_txns, encoding
        )
        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    def test_output(
        self,
        filepaths_recon_copy,
        injection_output,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_content,
        expected_x_content,
        expected_rx_content,
    ):
        """Test for passing `output`."""
        f = m.reconcile_new_txns
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        ledgers = [str(filepath) for filepath in (rx_path, x_path)]

        mock_input(input_responses)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            f(str(extraction), ledgers, output=str(injection_output))

        expected_print = self.get_expected_print(
            12, 6, x_path, rx_path, injection_output
        )
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            injection_output, expected_injection_content, extraction_txns, encoding
        )
        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    def test_remove(
        self,
        filepaths_recon_copy,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_content,
    ):
        """Test for `remove` option."""
        f = m.reconcile_new_txns
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        expected_rx_content = rx_path.read_text(encoding)
        expected_x_content = x_path.read_text(encoding)

        ledgers = [str(filepath) for filepath in (rx_path, x_path)]

        mock_input(input_responses)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            f(str(extraction), ledgers, remove=False)

        expected_print = textwrap.dedent(
            rf"""
            18 incoming transactions have been reconciled against expected transactions.
            Updated transactions have been output to '{extraction}'.
            """
        )
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            extraction, expected_injection_content, extraction_txns, encoding
        )
        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    def test_ascending(
        self,
        filepaths_recon_copy,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_ascending_content,
        expected_injection_content,
        expected_x_content,
        expected_rx_content,
    ):
        """Test for default options."""
        f = m.reconcile_new_txns
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        ledgers = [str(filepath) for filepath in (rx_path, x_path)]

        mock_input(input_responses)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            f(str(extraction), ledgers, ascending=False)

        expected_print = self.get_expected_print(12, 6, x_path, rx_path, extraction)
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            extraction, expected_injection_ascending_content, extraction_txns, encoding
        )
        assert len(expected_injection_ascending_content) == len(
            expected_injection_content
        )

        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    @pytest.mark.usefixtures("cwd_as_temp_dir")
    def test_cli_recon_default(
        self,
        filepaths_recon_copy,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_content,
        expected_x_content,
        expected_rx_content,
    ):
        """Test calling `reconcile_new_txns` via cli for with default options.

        Test based on `test_default`.
        """
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        mock_input(input_responses)
        output = io.StringIO()
        set_cl_args("recon extraction rx x")
        with contextlib.redirect_stdout(output):
            cli.main()

        expected_print = self.get_expected_print(12, 6, x_path, rx_path, extraction)
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            extraction, expected_injection_content, extraction_txns, encoding
        )
        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    @pytest.mark.usefixtures("cwd_as_temp_dir")
    def test_cli_recon_output(
        self,
        filepaths_recon_copy,
        injection_output,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_content,
        expected_x_content,
        expected_rx_content,
    ):
        """Test calling `reconcile_new_txns` via cli with output option.

        Test based on `test_output`.
        """
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]

        mock_input(input_responses)
        output = io.StringIO()
        set_cl_args("recon extraction rx x --output injection")
        with contextlib.redirect_stdout(output):
            cli.main()

        expected_print = self.get_expected_print(
            12, 6, x_path, rx_path, injection_output
        )
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            injection_output, expected_injection_content, extraction_txns, encoding
        )
        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    @pytest.mark.usefixtures("cwd_as_temp_dir")
    def test_cli_recon_remove(
        self,
        filepaths_recon_copy,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_content,
    ):
        """Test calling `reconcile_new_txns` via cli with remove option as False

        Test based on `test_remove`.
        """
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        expected_rx_content = rx_path.read_text(encoding)
        expected_x_content = x_path.read_text(encoding)

        mock_input(input_responses)
        output = io.StringIO()
        set_cl_args("recon extraction rx x -k")
        with contextlib.redirect_stdout(output):
            cli.main()

        expected_print = textwrap.dedent(
            rf"""
            18 incoming transactions have been reconciled against expected transactions.
            Updated transactions have been output to '{extraction}'.
            """
        )
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            extraction, expected_injection_content, extraction_txns, encoding
        )
        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)

    @pytest.mark.usefixtures("cwd_as_temp_dir")
    def test_cli_recon_ascending(
        self,
        filepaths_recon_copy,
        extraction_txns,
        mock_input,
        input_responses,
        encoding,
        expected_injection_ascending_content,
        expected_injection_content,
        expected_x_content,
        expected_rx_content,
    ):
        """Test calling `reconcile_new_txns` via cli with reverse option.

        Test based on `test_ascending`.
        """
        x_path = filepaths_recon_copy["x"]
        rx_path = filepaths_recon_copy["rx"]
        extraction = filepaths_recon_copy["extraction"]

        mock_input(input_responses)
        output = io.StringIO()
        set_cl_args("recon extraction rx x -r")
        with contextlib.redirect_stdout(output):
            cli.main()

        expected_print = self.get_expected_print(12, 6, x_path, rx_path, extraction)
        assert output.getvalue().endswith(expected_print)

        self.assert_expected_injection(
            extraction, expected_injection_ascending_content, extraction_txns, encoding
        )
        assert len(expected_injection_ascending_content) == len(
            expected_injection_content
        )

        assert expected_rx_content == rx_path.read_text(encoding)
        assert expected_x_content == x_path.read_text(encoding)
