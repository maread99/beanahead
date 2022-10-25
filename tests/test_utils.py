"""Tests for utils module."""

from collections import abc
import datetime
from decimal import Decimal
from pathlib import Path
import re
import textwrap

from beancount.core import data
import pytest

from beanahead import utils as m
from beanahead import errors

from .conftest import get_fileobj

# pylint: disable=missing-function-docstring, missing-type-doc, missing_class_docstring
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
def file_keys() -> abc.Iterator[set[str]]:
    yield {"x", "rx", "rx_def"}


@pytest.fixture
def ledger_file_keys() -> abc.Iterator[set[str]]:
    yield {"x", "rx"}


def test_constants(tag_x, tag_rx, file_keys, ledger_file_keys):
    """Test module constant values."""
    assert m.TAG_X == tag_x
    assert m.TAG_RX == tag_rx
    assert m.TAGS_X == set([tag_x, tag_rx])

    dflts = m.RX_META_DFLTS
    assert len(dflts) == 2
    assert dflts["final"] is None
    assert dflts["roll"] is True

    assert m.SEPARATOR_LINE.startswith("-")
    assert m.SEPARATOR_LINE.endswith("\n")
    assert m.TODAY == datetime.datetime.now().date()
    assert m.EXT == ".beancount"

    assert set(m.FILE_CONFIG.keys()) == set(file_keys)
    meta_keys = {"title", "plugin", "tag", "comment", "post_comment"}
    for k in file_keys:
        assert set(m.FILE_CONFIG[k].keys()) == meta_keys
    assert m.FILE_CONFIG["x"]["plugin"] is None
    assert m.FILE_CONFIG["x"]["tag"] == tag_x
    for file_key in ["rx", "rx_def"]:
        assert m.FILE_CONFIG[file_key]["plugin"] == "rx_txn_plugin"
        assert m.FILE_CONFIG[file_key]["tag"] == tag_rx

    assert set(m.LEDGER_FILE_KEYS) == ledger_file_keys


def test_validate_file_key(file_keys):
    f = m.validate_file_key
    for k in file_keys:
        assert f(k) is None
    for k in [file_keys.pop().upper(), "a"]:
        with pytest.raises(ValueError, match=f"'{k}' is not a valid file key"):
            f(k)


def test_validate_ledger_file_key(ledger_file_keys):
    f = m.validate_ledger_file_key
    for k in ledger_file_keys:
        assert f(k) is None
    for k in [ledger_file_keys.pop().upper(), "b"]:
        with pytest.raises(ValueError, match=f"'{k}' is not a valid ledger file key"):
            f(k)


def test_compose_header_footer():
    f = m.compose_header_footer

    expected_start = textwrap.dedent(
        """
        option "title" "Regular Expected Transactions Ledger"
        plugin "rx_txn_plugin"
        pushtag #rx_txn
        ;; Transactions should not be manually added to this file.
        """
    )
    expected_rx = (expected_start[1:], "poptag #rx_txn\n")
    assert f("rx") == expected_rx

    expected_rx_def_start = textwrap.dedent(
        """
        option "title" "Regular Expected Transaction Definitions"
        plugin "rx_txn_plugin"
        pushtag #rx_txn
        ;; All accounts referenced by definitions should be defined on the main ledger.
        ;; Enter definitions after this line...
        """
    )[1:]
    expected_rx_def_end = textwrap.dedent(
        """
        ;; ...enter definitions before this line.
        poptag #rx_txn
        """
    )[1:]
    assert f("rx_def") == (expected_rx_def_start, expected_rx_def_end)


def test_create_beanahead_file(files_make, cwd_as_temp_dir):
    f = m.create_beanahead_file

    make_contents = {k: fileobj.read() for k, fileobj in files_make.items()}

    def assertions(expected_path: Path, file_key: str):
        assert expected_path.is_file()
        with get_fileobj(expected_path) as file:
            assert file.read() == make_contents[file_key]

    # verify default behaviour
    for key in files_make:
        expected_path = cwd_as_temp_dir / f"{key}.beancount"
        assert not expected_path.is_file()
        f(key)
        assertions(expected_path, key)

    # verify can pass filename
    key = "rx"
    filename = "rx_alt"
    expected_path = cwd_as_temp_dir / f"{filename}.beancount"
    assert not expected_path.is_file()
    f(key, filename=filename)
    assertions(expected_path, key)

    # verify can pass dirpath
    key = "x"
    rel_path = "./_temp2"
    expected_path = cwd_as_temp_dir / rel_path / f"{key}.beancount"
    assert not expected_path.is_file()
    f(key, dirpath=rel_path)
    assertions(expected_path, key)

    # verify can pass dirpath and filename
    key = "rx_def"
    expected_path = cwd_as_temp_dir / rel_path / f"{filename}.beancount"
    assert not expected_path.is_file()
    f(key, dirpath=rel_path, filename=filename)
    assertions(expected_path, key)

    # verify raises error when filepath already exists
    with pytest.raises(FileExistsError, match=f"{expected_path.stem}"):
        f(key, dirpath=rel_path, filename=filename)

    # verify raises error when dirpath does not exists
    dirname = "not_a_directory"
    with pytest.raises(NotADirectoryError, match=f"{dirname}"):
        f(key, dirpath="./" + dirname)


def test_verify_path(filepath_ledger, filepath_no_file, filepath_empty_txt_file):
    f = m.verify_path
    # check verifies valid beancount file
    f(filepath_ledger)

    ExceptionCls = errors.BeancountFileExistsError
    # check raises error when path doesn't represent existing file
    with pytest.raises(ExceptionCls, match=f"{filepath_no_file.stem}"):
        f(filepath_no_file)

    # check raises error when path exists but doesn't have beancount ext
    match = "path does not have a '.beancount' extension."
    with pytest.raises(ExceptionCls, match=match):
        f(filepath_empty_txt_file)


def test_verify_files_key(filepaths_make, filepath_ledger, filepath_empty_txt_file):
    f = m.verify_files_key

    # check verifies valid beanahead files
    for k, path in filepaths_make.items():
        f(path, k)

    ExceptionCls = errors.BeanaheadFileKeyError
    filekey_actual = "x"

    def get_match(path: Path) -> str:
        return f"The first line of '{path}' does not contain the expected title"

    filekey_checked = "rx"

    def check_raises(path: Path):
        with pytest.raises(ExceptionCls, match=re.escape(get_match(path))):
            f(path, filekey_checked)

    # check raises error when filekey doesn't match the nature of beanahead file
    path = filepaths_make[filekey_actual]
    check_raises(path)
    # check raises error when filekey not a beanahead file
    check_raises(filepath_ledger)
    # ...or even a beancount file
    check_raises(filepath_empty_txt_file)


def test_get_unverified_path(cwd_as_temp_dir):
    f = m.get_unverified_path
    filename = "not_a_real_file"
    expected_path = cwd_as_temp_dir / (filename + ".beancount")
    assert f(filename) == expected_path  # verify relative
    assert f(filename + ".beancount") == expected_path  # verify with suffix
    assert f(str(expected_path)) == expected_path  # verify absolute


def test_get_verified_path(cwd_as_make_dir, filepath_make_x, filepath_no_file):
    f = m.get_verified_path
    assert f("x") == filepath_make_x
    assert f("x", "x") == filepath_make_x

    with pytest.raises(errors.BeanaheadFileKeyError):
        assert f("x", "rx")

    with pytest.raises(errors.BeancountFileExistsError):
        f(filepath_no_file.as_posix())


def test_get_options(filepath_make_rx):
    expected = "Regular Expected Transactions Ledger"
    assert m.get_options(filepath_make_rx)["title"] == expected


def test_get_verified_file_key(filepaths_make, filepath_no_file, filepath_ledger):
    """Also tests `get_verified_ledger_file_key`."""
    for f in (m.get_verified_file_key, m.get_verified_ledger_file_key):
        for k, path in filepaths_make.items():
            if k == "rx_def" and f is m.get_verified_ledger_file_key:
                continue
            assert f(path) == k

        # check verifying path to a beancount file
        with pytest.raises(errors.BeancountFileExistsError):
            f(filepath_no_file)

        # check verifying that a beanahead file
        path = filepath_ledger
        match = f"'{path}' does not represent a beanahead file."
        with pytest.raises(errors.BeanaheadFileExistsError, match=re.escape(match)):
            f(path)

    # check m.get_verified_ledger_file_key raises if path not a beanahead ledger file
    with pytest.raises(errors.BeanaheadLedgerFileExistsError):
        m.get_verified_ledger_file_key(filepaths_make["rx_def"])


class TestEntriesTxns:
    def assert_txns_equal(self, a: list[data.Transaction], b: list[data.Transaction]):
        """Assert two lists of transactions represent the same transactions.

        Assertions ignore attributes including meta.
        """
        assert len(a) == len(b)
        attrs = ["payee", "narration", "date"]
        attrs_postings = ["account", "units"]
        for txn_a, txn_b in zip(a, b):
            for attr in attrs:
                assert getattr(txn_a, attr) == getattr(txn_b, attr)
            assert len(txn_a.postings) == len(txn_b.postings)
            for post_a, post_b in zip(txn_a.postings, txn_b.postings):
                for attr in attrs_postings:
                    assert getattr(post_a, attr) == getattr(post_b, attr)

    def test_extract_entries(self, entries_ledger, txns_ledger):
        txns_rtrn = m.extract_txns(entries_ledger)
        self.assert_txns_equal(txns_rtrn, txns_ledger)

    def test_get_entries(self, filepath_ledger, entries_ledger, filepath_recon_rx):
        """Tests getting unverified and verified entries."""
        for f in (m.get_unverified_entries, m.get_verified_entries):
            assert f(filepath_ledger) == entries_ledger

        with pytest.raises(errors.BeancountLoaderErrors):
            f(filepath_recon_rx)  # errors on "Invalid reference to unknown account"

    def test_get_txns(self, filepath_ledger, txns_ledger, filepath_recon_rx):
        """Tests getting unverified and verified txns."""
        for f in (m.get_unverified_txns, m.get_verified_txns):
            self.assert_txns_equal(f(filepath_ledger), txns_ledger)

        with pytest.raises(errors.BeancountLoaderErrors):
            f(filepath_recon_rx)  # errors on "Invalid reference to unknown account"

    def test_is_expired(self, txn, monkeypatch):
        attr = "beanahead.utils.TODAY"
        monkeypatch.setattr(attr, txn.date - datetime.timedelta(1))
        assert not m.is_expired(txn)
        monkeypatch.setattr(attr, txn.date)
        assert not m.is_expired(txn)
        monkeypatch.setattr(attr, txn.date + datetime.timedelta(1))
        assert m.is_expired(txn)

    def test_get_expired_txns(self, txns_ledger, monkeypatch):
        attr = "beanahead.utils.TODAY"
        i = 13
        cut_off_txn = txns_ledger[i]
        assert cut_off_txn.date < txns_ledger[i + 1].date
        monkeypatch.setattr(attr, cut_off_txn.date + datetime.timedelta(1))
        rtrn = m.get_expired_txns(txns_ledger)
        self.assert_txns_equal(rtrn, txns_ledger[: i + 1])

    def test_remove_txns(self, txns_ledger):
        indices = [4, 17, 21]
        to_remove = [txns_ledger[i] for i in indices]
        rtrn = m.remove_txns(txns_ledger, to_remove)
        # assert len(rtrn) == len(txns_ledger) - len(indices)
        expected = (
            txns_ledger[:4] + txns_ledger[5:17] + txns_ledger[18:21] + txns_ledger[22:]
        )
        assert rtrn == expected

        match = (
            "The following items are in `txns_to_remove` although not"
            f" in `txns`:\n{to_remove}."
        )
        with pytest.raises(ValueError, match=re.escape(match)):
            m.remove_txns(rtrn, to_remove + txns_ledger[7:10])

    def test_reverse_automatic_balancing(self, txn):
        posting = txn.postings[1]
        assert posting.units is not None
        assert "__automatic__" in posting.meta
        revised_posting = data.Posting(
            posting.account,
            None,
            posting.cost,
            posting.price,
            posting.flag,
            {"filename": posting.meta["filename"], "lineno": posting.meta["lineno"]},
        )
        revised_postings = [txn.postings[0], revised_posting]

        expected = data.Transaction(
            txn.meta,
            txn.date,
            txn.flag,
            txn.payee,
            txn.narration,
            txn.tags,
            txn.links,
            revised_postings,
        )
        rtrn = m.reverse_automatic_balancing(txn)
        assert rtrn == expected

    def test_get_balance_sheet_accounts(self, txn_payroll):
        rtrn = m.get_balance_sheet_accounts(txn_payroll)
        assert rtrn == [
            "Assets:US:BofA:Checking",
            "Assets:US:Vanguard:Cash",
            "Liabilities:US:Chase:Slate",
            "Assets:US:Federal:PreTax401k",
            "Assets:US:BayBook:Vacation",
        ]


def test_get_content(filepath_ledger):
    contents = m.get_content(filepath_ledger)
    assert contents.startswith(
        ";; -*- mode: org; mode: beancount; -*-\n"
        ";; Birth: 1980-05-12\n"
        ";; Dates: 2020-01-01 - 2022-08-25\n"
        ";; THIS FILE HAS BEEN AUTO-GENERATED by beancount script\n"
        "* Options\n\n"
        'option "title" "Example Beancount file"\n'
        'option "operating_currency" "USD"\n'
    )
    assert contents.endswith(
        "2020-01-31 price ITOT                               88.49 USD\n"
        "2020-01-31 price VEA                               167.84 USD\n"
        "2020-01-31 price VHT                               127.70 USD\n"
        "2020-01-31 price GLD                               164.84 USD"
    )


def test_clean_rx_meta(rx_txn_chase):
    txn = rx_txn_chase
    assert "roll" in txn.meta
    # 'final' retained as not a default value, 'roll' removed as default True
    retained_keys = [
        "filename",
        "lineno",
        "final",
        "freq",
        "test_meta",
        "__tolerances__",
    ]
    meta = {k: txn.meta[k] for k in retained_keys}
    expected = data.Transaction(
        meta,
        txn.date,
        txn.flag,
        txn.payee,
        txn.narration,
        txn.tags,
        txn.links,
        txn.postings,
    )
    rtrn = m.clean_rx_meta(txn)
    assert rtrn == expected


def test_prepare_for_printing(rx_txn_chase, tag_rx):
    txn = rx_txn_chase
    assert "roll" in txn.meta
    # 'final' retained as not a default value, 'roll' removed as default True
    retained_keys = [
        "filename",
        "lineno",
        "final",
        "freq",
        "test_meta",
        "__tolerances__",
    ]
    meta = {k: txn.meta[k] for k in retained_keys}

    posting = txn.postings[1]
    assert posting.units is not None
    assert "__automatic__" in posting.meta
    revised_posting = data.Posting(
        posting.account,
        None,
        posting.cost,
        posting.price,
        posting.flag,
        {"filename": posting.meta["filename"], "lineno": posting.meta["lineno"]},
    )
    revised_postings = [txn.postings[0], revised_posting]

    assert tag_rx in txn.tags  # will be removed
    expected = data.Transaction(
        meta,
        txn.date,
        txn.flag,
        txn.payee,
        txn.narration,
        frozenset(["retained-tag"]),
        txn.links,
        revised_postings,
    )
    rtrn = m.prepare_for_printer(txn)
    assert rtrn == expected


def test_compose_entries_content(rx_txn_chase, txns_rx, txns_rx_content):
    # verify can pass a single entry, also tests removing
    f = m.compose_entries_content
    txn = rx_txn_chase
    expected = textwrap.dedent(
        """
        2022-10-31 * "Chase" "Chase Hire Purchase" #retained-tag
          final: 2022-11-30
          freq: "BM"
          test_meta: "Test meta on Chase HP"
          Liabilities:US:Chase:HirePurchase  322.00 USD
          Assets:US:BofA:Checking
        """
    )[1:]
    assert f(txn) == expected

    # check a balance_dir to make sure included unchanged in contents
    balance_dir = data.Balance(
        {},
        datetime.date(1990, 1, 1),
        "Assets:US:BofA:Checking",
        data.Amount(Decimal(3), "USD"),
        tolerance=None,
        diff_amount=None,
    )
    expected = (
        "1990-01-01 balance Assets:US:BofA:Checking                         3 USD\n"
    )
    assert f(balance_dir) == expected

    # check can pass as a list of entries
    txns_rx.insert(0, balance_dir)
    rtrn = f(txns_rx)
    expected += "\n" + txns_rx_content
    assert rtrn == expected


def test_compose_new_content(filepath_rx_content, txns_rx_content, encoding):
    f = m.compose_new_content
    file_key = "rx"
    rtrn = f(file_key, txns_rx_content)
    assert rtrn == filepath_rx_content

    match = re.escape(
        "New content parses with following errors: "
        """[LexerError(source={'filename': '<string>', 'lineno': 7}, message='Invalid"""
        r""" token: \'ee"\'', entry=None)]"""
    )

    with pytest.raises(ValueError, match=match):
        f(file_key, txns_rx_content[23:])


def test_write_and_overwrite(temp_dir, encoding, filepath_rx_content):
    """Tests `m.write` and `m.overwrite_file`."""
    path = temp_dir / "_test_write.txt"
    content = "Cóñtént"
    m.write(path, content)
    assert path.read_text(encoding) == content

    m.overwrite_file(path, filepath_rx_content)
    assert path.read_text(encoding) == filepath_rx_content

    match = re.escape(
        "_test_write.txt has not been overwritten as content would parse with"
        " the following errors: [LexerError(source={'filename': '<string>',"
        """ 'lineno': 1}, message="Invalid token: 'lugin'", entry=None)"""
    )
    with pytest.raises(ValueError, match=match):
        m.overwrite_file(path, filepath_rx_content[55:])


def test_create_ledger_content(filepath_rx_content, txns_rx):
    rtrn = m.create_ledger_content("rx", txns_rx)
    assert rtrn == filepath_rx_content


def test_remove_txns_from_ledger(filepath_rx_copy, txns_rx_copy, encoding, ans_dir):
    indices_to_remove = [2, 4, 10]
    to_remove = [txns_rx_copy[i] for i in indices_to_remove]

    # check removing txns expected...
    dates = (
        datetime.date(2022, 10, 7),
        datetime.date(2022, 10, 7),
        datetime.date(2022, 10, 31),
    )
    payees = ("BayBook", "RGAGX", "Slate")
    for txn, date, payee in zip(to_remove, dates, payees):
        assert txn.date == date
        assert txn.payee == payee

    m.remove_txns_from_ledger(filepath_rx_copy, to_remove)
    contents = filepath_rx_copy.read_text(encoding)
    expected = (ans_dir / "example_rx_txns_rmvd.beancount").read_text(encoding)
    assert contents == expected


def test_inject_txns(
    filepath_rx,
    filepath_rx_content,
    filepath_ledger_copy,
    filepath_ledger_content,
    encoding,
):
    injection = str(filepath_rx)
    ledger = str(filepath_ledger_copy)
    m.inject_txns(injection, ledger)
    new_contents = filepath_ledger_copy.read_text(encoding)
    assert new_contents == filepath_ledger_content + "\n" + filepath_rx_content


def test_add_remove_tags(rx_txn_chase, tag_rx):
    txn = rx_txn_chase
    existing_tags = [tag_rx, "retained-tag"]
    assert txn.tags == set(existing_tags)  # check working with txn as assumed

    rtrn = m.remove_tags(txn, tag_rx)  # pass as single tag
    assert rtrn == txn._replace(tags=frozenset(["retained-tag"]))

    rtrn = m.remove_tags(txn, existing_tags)  # pass as list of tags
    assert rtrn == txn._replace(tags=frozenset())

    rtrn = m.add_tags(txn, "new-tag")  # pass as single tag
    expected_tags = existing_tags
    expected_tags.append("new-tag")
    assert rtrn == txn._replace(tags=frozenset(expected_tags))

    rtrn = m.add_tags(txn, ["new-tag", "new-tag2"])  # pass as list
    expected_tags.append("new-tag2")
    assert rtrn == txn._replace(tags=frozenset(expected_tags))
