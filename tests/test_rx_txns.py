"""Tests for `rx_txns` module."""

from collections import abc
import datetime
import re
from pathlib import Path
import shutil

import beancount
from beancount.core import data
import pandas as pd
import pytest

from beanahead import rx_txns as m
from beanahead import errors
from beanahead.scripts import cli

from . import cmn
from .conftest import set_cl_args, also_get_stderr

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
def defs_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "defs"


@pytest.fixture
def filepath_defs(defs_dir) -> abc.Iterator[Path]:
    yield defs_dir / "defs.beancount"


@pytest.fixture
def filepath_defs_ledger(defs_dir) -> abc.Iterator[Path]:
    yield defs_dir / "ledger.beancount"


@pytest.fixture
def filepath_defs_rx(defs_dir) -> abc.Iterator[Path]:
    yield defs_dir / "rx.beancount"


@pytest.fixture
def filepath_defs_ledger_with_error(defs_dir) -> abc.Iterator[Path]:
    yield defs_dir / "ledger_with_error.beancount"


@pytest.fixture
def defs(filepath_defs) -> abc.Iterator[list[data.Transaction]]:
    entries, errors, options = beancount.loader.load_file(filepath_defs)
    yield entries


@pytest.fixture
def def_verizon(defs) -> abc.Iterator[data.Transaction]:
    def_ = defs[6]
    assert def_.payee == "Verizon"
    assert def_.date == datetime.date(2022, 10, 16)
    yield def_


@pytest.fixture
def def_slate(defs) -> abc.Iterator[data.Transaction]:
    def_ = defs[7]
    assert def_.payee == "Slate"
    assert def_.date == datetime.date(2022, 10, 31)
    yield def_


@pytest.fixture
def def_chase(defs) -> abc.Iterator[data.Transaction]:
    def_ = defs[8]
    assert def_.payee == "Chase"
    assert def_.date == datetime.date(2022, 10, 31)
    yield def_


@pytest.fixture
def def_dividend(defs) -> abc.Iterator[data.Transaction]:
    def_ = defs[10]
    assert def_.payee == "Dividend"
    assert def_.date == datetime.date(2022, 12, 15)
    yield def_


@pytest.fixture
def def_rgagx(defs) -> abc.Iterator[data.Transaction]:
    def_ = defs[4]
    assert def_.payee == "RGAGX"
    assert def_.date == datetime.date(2022, 10, 7)
    yield def_


@pytest.fixture
def def_baybook(defs) -> abc.Iterator[data.Transaction]:
    def_ = defs[2]
    assert def_.payee == "BayBook"
    assert def_.date == datetime.date(2022, 10, 7)
    yield def_


@pytest.fixture
def filepaths_defs_copy_0(
    filepath_defs, filepath_defs_rx, filepath_defs_ledger, temp_dir
) -> abc.Iterator[dict[str, Path]]:
    """Filepaths to files before generating regular transactions.

    Copies each of the defs files to temporary folder.

    Yields mapping to temporary paths with keys as:
        "defs" - Regular Transactions Definitions File
        "rx" - Regular Transactions Ledger
        "ledger" - Main ledger which references ledger 'rx'.
    """
    d = {}
    for k, filepath in zip(
        ("defs", "rx", "ledger"),
        (filepath_defs, filepath_defs_rx, filepath_defs_ledger),
    ):
        string = shutil.copy(filepath, temp_dir)
        d[k] = Path(string)
    yield d
    for path in d.values():
        path.unlink()


# Tests


def test_constants():
    """Test module constants."""
    end_dflt = datetime.datetime.now().date() + datetime.timedelta(weeks=13)
    try:
        assert m.END_DFLT == end_dflt
    except AssertionError:  # if tests started before 00:00 and now > 00:00
        assert m.END_DFLT == end_dflt - datetime.timedelta(1)

    assert m.SIMPLE_FREQ_MAPPING == {"w": "weeks", "m": "months", "y": "years"}

    assert m.OTHER_SIDE_ACCOUNTS == {
        "Assets": 0,
        "Income": 1,
        "Expenses": 2,
        "Various": 3,
    }

    assert m.VALID_FILE_KEYS == ["rx", "rx_def"]


def test_get_freq_offset(rx_txn_chase, rx_txn_edison):
    f = m.get_freq_offset
    assert f(rx_txn_chase) == pd.offsets.BusinessMonthEnd()
    assert f(rx_txn_edison) == pd.DateOffset(months=1)


def test_create_entries_and_final_roll(def_chase, def_verizon, monkeypatch):
    """Test various functions.

    Tests:
        `m.create_entries`
        `m.remove_after_final`
        `m.roll_txns`
    """
    f = m.create_entries

    # verify pandas frequency and passing `end`
    expected_dates = [
        datetime.date(2022, 10, 31),
        datetime.date(2022, 11, 30),
        datetime.date(2022, 12, 30),
        datetime.date(2023, 1, 31),
        datetime.date(2023, 2, 28),
    ]
    expected_new_def_date = datetime.date(2023, 3, 31)

    def_date = def_chase.date
    rtrn_txns, rtrn_def = f(def_chase, datetime.date(2023, 2, 28))

    for txn, date in zip(rtrn_txns, expected_dates):
        assert txn.date == date
        # verify otherwise as definition
        assert txn._replace(date=def_date) == def_chase

    assert rtrn_def.date == expected_new_def_date
    assert rtrn_def._replace(date=def_date) == def_chase

    # an aside to test `remove_after_final`
    # check def as assumed...
    assert def_chase.meta["final"] == datetime.date(2022, 11, 30)
    assert m.remove_after_final(rtrn_txns) == rtrn_txns[:2]

    # verify return when no transactions to generate
    rtrn = f(def_chase, datetime.date(2022, 10, 30))
    assert rtrn == ([], None)

    # verify edge where one transaction generated
    rtrn = f(def_chase, datetime.date(2022, 10, 31))
    assert len(rtrn[0]) == 1
    assert rtrn[0][0] == rtrn_txns[0]
    assert rtrn[1] == rtrn_txns[1]

    # verify default end date and for monthly freq
    monkeypatch.setattr("beanahead.rx_txns.END_DFLT", datetime.date(2023, 9, 23))
    expected_dates = [
        datetime.date(2022, 10, 16),
        datetime.date(2022, 11, 16),
        datetime.date(2022, 12, 16),
        datetime.date(2023, 1, 16),
        datetime.date(2023, 2, 16),
        datetime.date(2023, 3, 16),
        datetime.date(2023, 4, 16),
        datetime.date(2023, 5, 16),
        datetime.date(2023, 6, 16),
        datetime.date(2023, 7, 16),
        datetime.date(2023, 8, 16),
        datetime.date(2023, 9, 16),
    ]
    expected_new_def_date = datetime.date(2023, 10, 16)

    def_date = def_verizon.date
    rtrn_txns, rtrn_def = f(def_verizon, None)

    for txn, date in zip(rtrn_txns, expected_dates):
        assert txn.date == date
        # verify otherwise as definition
        assert txn._replace(date=def_date) == def_verizon

    assert rtrn_def.date == expected_new_def_date
    assert rtrn_def._replace(date=def_date) == def_verizon

    # an aside to test `roll_txns`
    # check def as assumed...
    assert def_verizon.meta["roll"]
    rolled = m.roll_txns(rtrn_txns)
    expected_rolled_dates = [
        datetime.date(2022, 10, 17),  # sunday rolled to monday
        datetime.date(2022, 11, 16),
        datetime.date(2022, 12, 16),
        datetime.date(2023, 1, 16),
        datetime.date(2023, 2, 16),
        datetime.date(2023, 3, 16),
        datetime.date(2023, 4, 17),  # sunday rolled to monday
        datetime.date(2023, 5, 16),
        datetime.date(2023, 6, 16),
        datetime.date(2023, 7, 17),  # sunday rolled to monday
        datetime.date(2023, 8, 16),  # saturday rolled to monday
        datetime.date(2023, 9, 18),
    ]
    for txn, date in zip(rolled, expected_rolled_dates):
        assert txn.date == date
        # verify otherwise as definition
        assert txn._replace(date=def_date) == def_verizon


def test_get_definition_group(
    def_slate, def_chase, def_rgagx, def_dividend, def_baybook
):
    f = m.get_definition_group
    assert f(def_slate) == ("Assets:US:BofA:Checking", "Expenses")
    assert f(def_chase) == ("Liabilities:US:Chase:HirePurchase", "Assets")
    assert f(def_rgagx) == ("Assets:US:Vanguard:Cash", "Assets")
    assert f(def_dividend) == ("Assets:US:ETrade:Cash", "Income")
    assert f(def_baybook) == ("Assets:US:BofA:Checking", "Various")


class TestAdmin:
    """Test public methods of Admin class.

    NOTE: Tests defined on this class are considered to cover all code on
    the `rx_txns` module that isn't otherwise covered by other tests of
    this module.
    """

    @pytest.fixture
    def defs_repeat_payee_filepath(self, defs_dir) -> abc.Iterator[Path]:
        yield defs_dir / "defs_repeat_payee.beancount"

    @pytest.fixture
    def defs_221231_filepath(self, defs_dir) -> abc.Iterator[Path]:
        yield defs_dir / "defs_221231.beancount"

    @pytest.fixture
    def defs_221231_content(self, defs_221231_filepath, encoding) -> abc.Iterator[str]:
        yield defs_221231_filepath.read_text(encoding)

    @pytest.fixture
    def defs_221231(self, defs_221231_filepath) -> abc.Iterator[list[data.Transaction]]:
        defs, _, _ = beancount.loader.load_file(defs_221231_filepath)
        yield defs

    @pytest.fixture
    def rx_221231_filepath(self, defs_dir) -> abc.Iterator[Path]:
        yield defs_dir / "rx_221231.beancount"

    @pytest.fixture
    def rx_221231_content(self, rx_221231_filepath, encoding) -> abc.Iterator[str]:
        yield rx_221231_filepath.read_text(encoding)

    @pytest.fixture
    def rx_txns_221231(
        self, rx_221231_filepath
    ) -> abc.Iterator[list[data.Transaction]]:
        txns, _, _ = beancount.loader.load_file(rx_221231_filepath)
        yield txns

    @pytest.fixture
    def defs_230630_filepath(self, defs_dir) -> abc.Iterator[Path]:
        yield defs_dir / "defs_230630.beancount"

    @pytest.fixture
    def defs_230630_content(self, defs_230630_filepath, encoding) -> abc.Iterator[str]:
        yield defs_230630_filepath.read_text(encoding)

    @pytest.fixture
    def defs_230630(self, defs_230630_filepath) -> abc.Iterator[list[data.Transaction]]:
        defs, _, _ = beancount.loader.load_file(defs_230630_filepath)
        yield defs

    @pytest.fixture
    def rx_230630_filepath(self, defs_dir) -> abc.Iterator[Path]:
        yield defs_dir / "rx_230630.beancount"

    @pytest.fixture
    def rx_230630_content(self, rx_230630_filepath, encoding) -> abc.Iterator[str]:
        yield rx_230630_filepath.read_text(encoding)

    @pytest.fixture
    def rx_txns_230630(
        self, rx_230630_filepath
    ) -> abc.Iterator[list[data.Transaction]]:
        txns, _, _ = beancount.loader.load_file(rx_230630_filepath)
        yield txns

    def test_constructor_raises(
        self,
        filepaths_defs_copy_0,
        filepath_defs_ledger_with_error,
        defs_repeat_payee_filepath,
    ):
        """Test contructor raises error with ledger loads with errors."""
        defs, rx_ledger = filepaths_defs_copy_0["defs"], filepaths_defs_copy_0["rx"]
        with pytest.raises(errors.BeancountLoaderErrors):
            m.Admin(defs, rx_ledger, filepath_defs_ledger_with_error)

        # verify raises error if definitions' payees' not unique
        defs = defs_repeat_payee_filepath
        match = re.escape(
            "The payee of each regular expected transaction must be unique"
            " (case insensitive) although the following payees are"
            f" repeated in the file {defs}:\n['edison']."
        )
        with pytest.raises(errors.RegularTransactionsDefinitionError, match=match):
            m.Admin(defs, rx_ledger, filepath_defs_ledger_with_error)

    def test_admin(
        self,
        filepaths_defs_copy_0,
        defs,
        defs_221231_content,
        rx_221231_content,
        defs_221231,
        rx_txns_221231,
        defs_230630_content,
        rx_230630_content,
        encoding,
    ):
        """Test for initial generation of rx txns.

        Tests verifies rx txn ledgers and updated definitions against
        expected contents as provided by the following files. Whenever the
        `defs/defs.beancount` file is changed the following files should
        be reviewed to ensure that they reflect the required and expected
        contents.
            defs/defs.beancount - initial definitions

            rx_221231.beancount - should reflect rx txns ledger after
            adding regular expected transactions through to 22/12/31.

            defs_2221231.beancount - should reflect definitions file
            after having added regular transaction to the rx ledger
            through to 22/12/31.

            rx_230630.beancount - should reflect rx txns ledger after
            adding regular expected transactions through to 23/06/30.

            defs_2221231.beancount - should reflect definitions file
            after having added regular transaction to the rx ledger
            through to 23/06/30.

        22/10/26 - verified all above files as required and expected.
        """
        defs_path = filepaths_defs_copy_0["defs"]
        rx_path = filepaths_defs_copy_0["rx"]
        ledger_path = filepaths_defs_copy_0["ledger"]
        admin = m.Admin(defs_path, rx_path, ledger_path)

        def_payees = {
            "Account Fee",
            "EDISON",
            "BayBook",
            "VBMPX",
            "RGAGX",
            "Metro",
            "Verizon",
            "Slate",
            "Chase",
            "ETrade Transfer",
            "Dividend",
            "Erie",
        }

        cmn.assert_txns_equal(admin.rx_defs.values(), defs)
        assert set(admin.payees) == def_payees
        assert admin.rx_files == [defs_path, rx_path]
        assert admin.rx_txns == []

        _, output = also_get_stderr(admin.add_txns, datetime.date(2022, 12, 31))
        expected_output = (
            "42 transactions have been added to the ledger 'rx'.\n"
            "Definitions on 'defs' have been updated to reflect the"
            " most recent transactions.\n"
        )
        assert output == expected_output
        assert defs_path.read_text(encoding) == defs_221231_content
        assert rx_path.read_text(encoding) == rx_221231_content

        cmn.assert_txns_equal(admin.rx_defs.values(), defs_221231)
        def_payees.remove("Chase")
        assert set(admin.payees) == def_payees
        assert admin.rx_files == [defs_path, rx_path]
        cmn.assert_txns_equal(admin.rx_txns, rx_txns_221231)

        _, output = also_get_stderr(admin.add_txns, datetime.date(2023, 6, 30))
        expected_output = (
            "80 transactions have been added to the ledger 'rx'."
            "\nDefinitions on 'defs' have been updated to reflect the"
            " most recent transactions.\n"
        )
        assert output == expected_output
        assert defs_path.read_text(encoding) == defs_230630_content
        assert rx_path.read_text(encoding) == rx_230630_content

    @pytest.mark.usefixtures("cwd_as_temp_dir")
    def test_cli_addrx(
        self,
        filepaths_defs_copy_0,
        defs_221231_content,
        rx_221231_content,
        defs_230630_content,
        rx_230630_content,
        encoding,
    ):
        """Test calling `Admin.add_txns` via cli.

        Test based on `test_admin`.
        """
        defs_path = filepaths_defs_copy_0["defs"]
        rx_path = filepaths_defs_copy_0["rx"]

        set_cl_args("addrx defs rx ledger -e 2022-12-31")
        _, output = also_get_stderr(cli.main)
        expected_output = (
            "42 transactions have been added to the ledger 'rx'.\n"
            "Definitions on 'defs' have been updated to reflect the"
            " most recent transactions.\n"
        )
        assert output == expected_output
        assert defs_path.read_text(encoding) == defs_221231_content
        assert rx_path.read_text(encoding) == rx_221231_content

        set_cl_args("addrx defs rx ledger -e 2023-06-30")
        _, output = also_get_stderr(cli.main)
        expected_output = (
            "80 transactions have been added to the ledger 'rx'."
            "\nDefinitions on 'defs' have been updated to reflect the"
            " most recent transactions.\n"
        )
        assert output == expected_output
        assert defs_path.read_text(encoding) == defs_230630_content
        assert rx_path.read_text(encoding) == rx_230630_content
