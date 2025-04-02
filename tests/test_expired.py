"""Tests for `expired` module."""

from collections import abc
import datetime
from pathlib import Path
import re
import shutil

import pytest

from beanahead import expired as m
from beanahead import errors
from beanahead.scripts import cli

from .conftest import get_entries_from_string, set_cl_args, get_expected_output

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
def expired_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "expired"


@pytest.fixture
def filepaths_copy(expired_dir, temp_dir) -> abc.Iterator[dict[str, Path]]:
    """Filepaths to copies of files before administrating expired transactions.

    Copies of each file saved to temporary folder.

    Yields mapping to temporary paths with keys as:
        "rx" - expected regular transactions ledger
        "x" - expected transactions ledger
    """
    filepath_x = expired_dir / "x.beancount"
    filepath_rx = expired_dir / "rx.beancount"
    d = {}
    for k, filepath in zip(("rx", "x"), (filepath_rx, filepath_x)):
        string = shutil.copy(filepath, temp_dir)
        d[k] = Path(string)
    yield d
    for path in d.values():
        path.unlink()


def mock_today(today: datetime.date, monkeypatch):
    monkeypatch.setattr("beanahead.expired.TODAY", today)
    monkeypatch.setattr("beanahead.utils.TODAY", today)


def mock_tomorrow(tomorrow: datetime.date, monkeypatch):
    monkeypatch.setattr("beanahead.expired.TOMORROW", tomorrow)


def test_constants():
    now = datetime.datetime.now()
    today = now.date()
    try:
        assert m.TODAY == today
    except AssertionError:  # if tests started before 00:00 and now > 00:00
        assert now.hour == 0 and now.minute < 5
        today = today - datetime.timedelta(1)
        assert m.TODAY == today

    assert m.TOMORROW == today + datetime.timedelta(1)

    assert m.DATE_FORMATS == "(YYYY-MM-DD or MM-DD or DD)"

    assert m.VALID_DATE_FORMAT_REGEXES == [
        re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"),
        re.compile(r"^\d{1,2}-\d{1,2}$"),
        re.compile(r"^\d{1,2}$"),
    ]


def test_get_date_parts(monkeypatch):
    f = m._get_date_parts

    mock_today(datetime.date(2022, 11, 2), monkeypatch)
    assert f("2021-11-02") == (2021, 11, 2)
    assert f("2023-11-01") == f("11-01") == (2023, 11, 1)

    assert f("2022-11-02") == f("11-02") == f("02") == f("2") == (2022, 11, 2)
    assert f("2022-11-03") == f("11-03") == f("03") == f("3") == (2022, 11, 3)
    assert f("2022-12-01") == f("01") == f("1") == (2022, 12, 1)

    mock_today(datetime.date(2022, 12, 2), monkeypatch)
    assert f("2021-12-02") == (2021, 12, 2)
    assert f("2023-12-01") == f("12-01") == (2023, 12, 1)

    assert f("2022-12-02") == f("12-02") == f("02") == f("2") == (2022, 12, 2)
    assert f("2022-12-03") == f("12-03") == f("03") == f("3") == (2022, 12, 3)
    assert f("2023-01-01") == f("01") == f("1") == (2023, 1, 1)


def test_get_from_response(monkeypatch):
    f = m._get_date_from_response

    assert f("22-08-15") is None  # verify invalid date format returns None
    assert f("2022-15-08") is None  # verify invalid date returns None

    # verify valid input returns as expected
    mock_today(datetime.date(2022, 12, 2), monkeypatch)
    assert f("2021-12-02") == datetime.date(2021, 12, 2)
    assert f("2023-12-01") == f("12-01") == datetime.date(2023, 12, 1)

    assert f("2022-12-02") == f("12-02") == f("02") == datetime.date(2022, 12, 2)
    assert f("2022-12-03") == f("12-03") == f("03") == datetime.date(2022, 12, 3)
    assert f("2023-01-01") == f("01") == f("1") == datetime.date(2023, 1, 1)


def test_update_txn(monkeypatch, mock_input, capsys):
    f = m._update_txn
    mock_today(datetime.date(2022, 11, 15), monkeypatch)
    tomorrow = datetime.date(2022, 11, 16)
    mock_tomorrow(tomorrow, monkeypatch)

    input_ = """
        2022-10-15 * "Payee" ""
          Assets:US:BofA:Checking                  -52.44 USD
        """
    txn = get_entries_from_string(input_)[0]
    path = Path("dummy/path/to/x.beancount")

    expected_print = get_expected_output(
        r"""
        ---

        The following transaction has expired.

        2022-10-15 * "Payee" ""
          Assets:US:BofA:Checking  -52.44 USD

        0 Move transaction forwards to tomorrow (2022-11-16).
        1 Move transaction forwards to another date.
        2 Remove transaction from ledger x.
        3 Leave transaction as is.
        Choose one of the above options, [0-3]:
        """
    )

    mock_input((v for v in ["0"]))
    rtrn = f(txn, path)
    assert capsys.readouterr().out.endswith(expected_print)
    assert rtrn == txn._replace(date=tomorrow)

    mock_input((v for v in ["2"]))
    rtrn = f(txn, path)
    assert capsys.readouterr().out.endswith(expected_print)
    assert rtrn is None

    mock_input((v for v in ["3"]))
    rtrn = f(txn, path)
    assert capsys.readouterr().out.endswith(expected_print)
    assert rtrn is txn

    # verify handles invalid input
    expected_print_ = expected_print + (
        "'n' is not valid input, please try again, [0-3]: \n'y' is not"
        " valid input, please try again, [0-3]: \n'4' is not valid input,"
        " please try again, [0-3]: \n"
    )
    mock_input((v for v in ["n", "y", "4", "3"]))
    rtrn = f(txn, path)
    assert capsys.readouterr().out.endswith(expected_print_)
    assert rtrn is txn

    # verify option to enter a new date
    expected_print += "Enter a new date (YYYY-MM-DD or MM-DD or DD): \n"
    mock_input((v for v in ["1", "2022-12-03"]))
    rtrn = f(txn, path)
    assert capsys.readouterr().out.endswith(expected_print)
    assert rtrn == txn._replace(date=datetime.date(2022, 12, 3))

    # verify handles invalid date input
    expected_print += (
        "'22-12-03' does not represent a valid date.\nPlease enter a"
        " valid date (YYYY-MM-DD or MM-DD or DD): \n'2022-11-14' does"
        " not represent a date >= 2022-11-15.\nPlease enter a valid date"
        " (YYYY-MM-DD or MM-DD or DD): \n"
    )
    mock_input((v for v in ["1", "22-12-03", "2022-11-14", "2022-12-03"]))
    rtrn = f(txn, path)
    assert capsys.readouterr().out.endswith(expected_print)
    assert rtrn == txn._replace(date=datetime.date(2022, 12, 3))


def test_overwrite_ledgers(filepaths_recon_copy, encoding):
    x = filepaths_recon_copy["x"]
    rx = filepaths_recon_copy["rx"]
    x_first_line = 'option "title" "Expected Transactions Ledger"\n'
    rx_first_line = 'option "title" "Regular Expected Transactions Ledger"\n'
    orig_contents_x = x.read_text(encoding)
    orig_contents_rx = rx.read_text(encoding)
    assert orig_contents_x.startswith(x_first_line)
    assert orig_contents_rx.startswith(rx_first_line)

    chgd_x_contents = orig_contents_x.replace(x_first_line, "")
    chgd_rx_contents = orig_contents_x.replace(rx_first_line, "")
    m.overwrite_ledgers({x: chgd_x_contents, rx: chgd_rx_contents})
    assert x.read_text(encoding) == chgd_x_contents
    assert rx.read_text(encoding) == chgd_rx_contents

    # check raises and reverts when new contents would result in loading error
    invalid_contents_rx = orig_contents_rx[3:]
    with pytest.raises(errors.BeanaheadWriteError):
        m.overwrite_ledgers({x: orig_contents_x, rx: invalid_contents_rx})
    assert x.read_text(encoding) == chgd_x_contents
    assert rx.read_text(encoding) == chgd_rx_contents

    invalid_contents_x = orig_contents_x[3:]
    with pytest.raises(errors.BeanaheadWriteError):
        m.overwrite_ledgers({x: invalid_contents_x, rx: orig_contents_rx})
    assert x.read_text(encoding) == chgd_x_contents
    assert rx.read_text(encoding) == chgd_rx_contents

    with pytest.raises(errors.BeanaheadWriteError):
        m.overwrite_ledgers({x: invalid_contents_x, rx: invalid_contents_rx})
    assert x.read_text(encoding) == chgd_x_contents
    assert rx.read_text(encoding) == chgd_rx_contents

    m.overwrite_ledgers({x: orig_contents_x, rx: orig_contents_rx})
    assert x.read_text(encoding) != chgd_x_contents
    assert rx.read_text(encoding) != chgd_rx_contents

    assert x.read_text(encoding) == orig_contents_x
    assert rx.read_text(encoding) == orig_contents_rx


class TestAdminExpiredTxns:
    """Tests for function `admin_expired_txns`"""

    @pytest.fixture
    def expected_x(self, expired_dir, encoding) -> abc.Iterator[str]:
        filepath = expired_dir / "expected_x.beancount"
        yield filepath.read_text(encoding)

    @pytest.fixture
    def expected_rx(self, expired_dir, encoding) -> abc.Iterator[str]:
        filepath = expired_dir / "expected_rx.beancount"
        yield filepath.read_text(encoding)

    def test_all_options(
        self,
        monkeypatch,
        mock_input,
        filepaths_copy,
        expected_x,
        expected_rx,
        encoding,
        capsys,
    ):
        """Test all options for an expired transaction."""
        f = m.admin_expired_txns
        mock_today(datetime.date(2022, 11, 15), monkeypatch)
        tomorrow = datetime.date(2022, 11, 16)
        mock_tomorrow(tomorrow, monkeypatch)

        filepath_x = filepaths_copy["x"]
        filepath_rx = filepaths_copy["rx"]
        ledgers = [filepath_x, filepath_rx]

        expected_print = get_expected_output(
            rf"""
            The following ledgers have been updated:
            {filepath_x}
            {filepath_rx}
            """
        )
        mock_input((v for v in ["3", "0", "1", "2022-11-20", "2", "0"]))
        f(ledgers)
        assert capsys.readouterr().out.endswith(expected_print)
        assert filepath_x.read_text(encoding) == expected_x
        assert filepath_rx.read_text(encoding) == expected_rx

    def test_no_changes(
        self, monkeypatch, mock_input, filepaths_copy, encoding, capsys
    ):
        """Test all options for an expired transaction."""
        f = m.admin_expired_txns
        mock_today(datetime.date(2022, 11, 15), monkeypatch)
        tomorrow = datetime.date(2022, 11, 16)
        mock_tomorrow(tomorrow, monkeypatch)

        filepath_x = filepaths_copy["x"]
        orig_contents_x = filepath_x.read_text(encoding)

        expected_print = (
            "\nYou have not choosen to modify any expired transactions."
            "\nNo ledger has been altered.\n"
        )
        expected_print = expected_print[1:]
        mock_input((v for v in ["3", "3", "3", "3"]))
        f([str(filepath_x)])
        assert capsys.readouterr().out.endswith(expected_print)
        assert filepath_x.read_text(encoding) == orig_contents_x

    def test_none_expired(self, monkeypatch, filepaths_copy, encoding, capsys):
        """Test all options for an expired transaction."""
        f = m.admin_expired_txns
        mock_today(datetime.date(2022, 10, 1), monkeypatch)

        filepath_rx = filepaths_copy["rx"]
        filepath_x = filepaths_copy["x"]
        ledgers = [str(filepath_rx), str(filepath_x)]

        orig_contents_x = filepath_x.read_text(encoding)
        orig_contents_rx = filepath_rx.read_text(encoding)

        expected_print = get_expected_output(
            rf"""
            There are no expired transactions on any of the following ledgers:
            {filepath_rx}
            {filepath_x}
            """
        )
        f(ledgers)
        assert capsys.readouterr().out.endswith(expected_print)
        assert filepath_x.read_text(encoding) == orig_contents_x
        assert filepath_rx.read_text(encoding) == orig_contents_rx

    @pytest.mark.usefixtures("cwd_as_temp_dir")
    def test_cli_exp(
        self,
        monkeypatch,
        mock_input,
        filepaths_copy,
        expected_x,
        expected_rx,
        encoding,
        capsys,
    ):
        """Test calling via cli.

        Test based on `test_all_options`.
        """
        mock_today(datetime.date(2022, 11, 15), monkeypatch)
        tomorrow = datetime.date(2022, 11, 16)
        mock_tomorrow(tomorrow, monkeypatch)

        filepath_x = filepaths_copy["x"]
        filepath_rx = filepaths_copy["rx"]

        expected_print = get_expected_output(
            rf"""
            The following ledgers have been updated:
            {filepath_x}
            {filepath_rx}
            """
        )
        mock_input((v for v in ["3", "0", "1", "2022-11-20", "2", "0"]))
        set_cl_args("exp x rx")
        cli.main()
        assert capsys.readouterr().out.endswith(expected_print)
        assert filepath_x.read_text(encoding) == expected_x
        assert filepath_rx.read_text(encoding) == expected_rx

    @pytest.mark.usefixtures("cwd_as_temp_dir", "settings_alt_prnt_mp")
    def test_cli_exp_print_to_stderr(
        self,
        monkeypatch,
        mock_input,
        filepaths_copy,
        expected_x,
        expected_rx,
        encoding,
        capsys,
    ):
        """As `test_cli_exp` with print to stderr.

        Serves to test --print_stderr cli arg.
        """
        mock_today(datetime.date(2022, 11, 15), monkeypatch)
        tomorrow = datetime.date(2022, 11, 16)
        mock_tomorrow(tomorrow, monkeypatch)

        filepath_x = filepaths_copy["x"]
        filepath_rx = filepaths_copy["rx"]

        expected_print = get_expected_output(
            rf"""
            The following ledgers have been updated:
            {filepath_x}
            {filepath_rx}
            """
        )
        mock_input((v for v in ["3", "0", "1", "2022-11-20", "2", "0"]))
        set_cl_args("exp x rx")
        cli.main()
        assert capsys.readouterr().err.endswith(expected_print)
        assert filepath_x.read_text(encoding) == expected_x
        assert filepath_rx.read_text(encoding) == expected_rx
