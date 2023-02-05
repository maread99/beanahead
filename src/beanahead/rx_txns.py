"""Functions and class for administering regular transactions."""

from __future__ import annotations

import copy
from collections import defaultdict
import datetime
import functools
from pathlib import Path
import re

import pandas as pd
from beancount import loader
from beancount.core import data
from beancount.core.account_types import get_account_type
from beancount.core.data import Transaction
from beancount.parser import parser
from beancount.parser.printer import EntryPrinter

from . import utils, errors
from .errors import BeanaheadWriteError, BeancountLoaderErrors

END_DFLT = utils.TODAY + datetime.timedelta(weeks=13)

REGEX_SIMPLE_FREQ = re.compile(r"^\d*[mwy]$")
SIMPLE_FREQ_MAPPING = {
    "w": "weeks",
    "m": "months",
    "y": "years",
}


def is_simple_freq(string: str) -> bool:
    """Query if a string represents a simple frequency definition.

    Examples
    --------
    >>> simple_freqs = ["3m", "2y", "13w", "m", "y", "w", "1y"]
    >>> all(is_simple_freq(freq) for freq in simple_freqs)
    True
    >>> not_simple_freqs = ["3M", "2", "2r", "3mm"]
    >>> any(is_simple_freq(freq) for freq in not_simple_freqs)
    False
    """
    return REGEX_SIMPLE_FREQ.match(string) is not None


def get_simple_offset(freq: str) -> pd.DateOffset:
    """Return offset corresponding with a simple frequency.

    Parameters
    ----------
    freq
        Simple frequency, for example "y", "3m", "13w"

    Examples
    --------
    >>> get_simple_offset("3m")
    <DateOffset: months=3>
    >>> get_simple_offset("2y")
    <DateOffset: years=2>
    >>> get_simple_offset("13w")
    <DateOffset: weeks=13>
    >>> get_simple_offset("m")
    <DateOffset: months=1>
    >>> get_simple_offset("1m")
    <DateOffset: months=1>
    """
    unit = freq[-1]
    value = 1 if len(freq) == 1 else int(freq[:-1])
    kwargs = {SIMPLE_FREQ_MAPPING[unit]: value}
    return pd.DateOffset(**kwargs)


def get_freq_offset(txn: Transaction) -> pd.offsets.BaseOffset:
    """Get offset for a regular transaction.

    Parameters
    ----------
    txn
        Transaction to query.
    """
    freq = txn.meta["freq"]
    if is_simple_freq(freq):
        return get_simple_offset(freq)
    return pd.tseries.frequencies.to_offset(freq)


def create_entries(
    rx_def: Transaction, end: datetime.date
) -> tuple[list[Transaction], Transaction | None]:
    """Create entries and new definition for a regular transaction.

    Creates entries from rx_def through `end`. Creates new definition as
    earliest transaction following `end`.

    Parameters
    ----------
    rx_def
        Regular expected transaction definition. This is the unmodified
        version of the last entry created for the regular transaction
        (this should be the entry as defined on the rx_defs beancount
        file).

    end : datetime.date
        The end date up to which transactions should be created. The last
        transaction will be `end` if `end` coincides with a regular
        transaction, or otherwise the latest transaction that falls before
        `end`.

    Returns
    -------
    2-tuple
        [0] Transactions from `rx_def` through `end`, inclusive of
        `rx_def`.

        [1] New definition, as next transaction after `end`, or None if [0]
        is empty.

        For both items, transaction dates are as they fall based ONLY on
        the transaction frequency, i.e. transactions are NOT modified by,
        for example, rolling forwards over a weekend or any 'final' meta.
    """
    end = END_DFLT if end is None else end
    offset = get_freq_offset(rx_def)
    dates = pd.date_range(rx_def.date, end + offset, freq=offset)
    if len(dates) < 2:
        # no txns dated < end (only new definition date was evaluated)
        return ([], None)
    txns = []
    for date in dates:
        txn = copy.copy(rx_def)
        txn = txn._replace(date=date.date())
        txns.append(txn)
    new_def = txns.pop()
    return (txns, new_def)


def remove_after_final(txns: list[Transaction]) -> list[Transaction]:
    """Remove transactions dated after any final date."""
    return [
        txn
        for txn in txns
        if (txn.meta["final"] is None) or (txn.date <= txn.meta["final"])
    ]


def roll_txns(txns: list[Transaction]) -> list[Transaction]:
    """Roll transactions that roll forwards at weekend.

    Any transaction that is set to roll and falls on a weekend is replaced
    with a transaction dated on the following Monday.

    Parameters
    ----------
    txns
        Transactions to be rolled, if applicable.
    """
    weekend = [6, 7]
    rtrn = []
    for txn in txns:
        date = txn.date
        if txn.meta["roll"] and (dayofweek := date.isoweekday()) in weekend:
            new_date = date + datetime.timedelta(days=8 - dayofweek)
            rolled_txn = txn._replace(date=new_date)
            rtrn.append(rolled_txn)
        else:
            rtrn.append(txn)
    return rtrn


OTHER_SIDE_ACCOUNTS = {
    "Assets": 0,
    "Income": 1,
    "Expenses": 2,
    "Various": 3,
}

GrouperKey = tuple[str, str]


def get_definition_group(definition: Transaction) -> GrouperKey:
    """Return key of group corresponding with a definition.

    Parameters
    ----------
    definition
        Definition to query.

    Returns
    -------
    2-tuple of str
        [0] Balance sheet account. This will be the account of the first
        defined posting to either an "Assets" or "Liabilites" account.

        [1] Other-side account type. Type of accounts on 'other-side'. This
        will be a key of `OTHER_SIDE_ACCOUNTS`.
        "Liabilities" are treated as "Expenses" for the purpose of
        evaluate the other-side account type.
        "Various" if there are `other-side` postings to more than one type
        of account.

        Example: ("Assets:US:Chase:Checking", "Expenses")
    """
    bal_sheet_account = utils.get_balance_sheet_accounts(definition)[0]
    other_sides = set()
    for posting in definition.postings:
        account = posting.account
        if account == bal_sheet_account:
            continue
        account_type = get_account_type(account)
        if account_type == "Assets":
            other_sides.add("Assets")
        elif account_type == "Income":
            other_sides.add("Income")
        else:
            other_sides.add("Expenses")
    other_side = "Various" if len(other_sides) > 1 else other_sides.pop()
    return (bal_sheet_account, other_side)


def group_definitions(
    defs: list[Transaction],
) -> dict[GrouperKey, list[Transaction]]:
    """Group definitions.

    Parameters
    ----------
    defs
        Definitions to be grouped.

    Returns
    -------
    dict
        key : 2-tuple of str, str
            Definition group, as returned by `get_definition_group`.

        value : list of Transaction
            List of definitions corresponding with group.
    """
    grouper = defaultdict(list)
    for definition in defs:
        group = get_definition_group(definition)
        grouper[group].append(definition)
    return grouper


def sortkey_grouper(grouper_key: GrouperKey) -> tuple[str, str]:
    """sortkey for a GrouperKey.

    Sorts by:
        Assets account name
        Other side account type, in order:
            "Assets", "Liabilities", "Income", "Expenses", "Various"

    Parameters
    ----------
    grouper_key: tuple[str, str]
        [0] An assets account.

        [1] Type of other account, i.e. "Assets", "Income", "Expenses"
        or "Various".
    """
    return (grouper_key[0], OTHER_SIDE_ACCOUNTS[grouper_key[1]])


def get_group_heading(group: GrouperKey) -> str:
    """Return section heading for a definitions group.

    Parameters
    ----------
    group
        Definitions group for which require section heading.
    """
    bal_sheet_acc, other_side_type = group
    if other_side_type == "Assets":
        insert = "other " if utils.is_assets_account(bal_sheet_acc) else ""
        return f"Transactions between '{bal_sheet_acc}' and {insert}Assets accounts"
    elif other_side_type == "Expenses":
        return f"'{bal_sheet_acc}' to Expenses and Liabilities"
    elif other_side_type == "Income":
        return f"Income to '{bal_sheet_acc}'"
    elif other_side_type == "Various":
        return f"'{bal_sheet_acc}' to various account types"
    return "Other definitions"


def compose_definitions_content(txns: list[Transaction]) -> str:
    """Compose content for a Regular Expected Transaction Definitions file.

    Parameters
    ----------
    txns
        Transaction objects that content is to be comprised of.
    """
    grouper = group_definitions(txns)
    content = ""
    printer = EntryPrinter()
    for key in sorted(grouper.keys(), key=sortkey_grouper):
        content += f"* {get_group_heading(key)}\n"
        group_txns = grouper[key]
        group_txns.sort(key=lambda txn: txn.payee)
        for txn in group_txns:
            txn = utils.prepare_for_printer(txn)
            content += "\n" + printer(txn)
        content += "\n\n"
    return content


VALID_FILE_KEYS = ["rx", "rx_def"]


def compose_new_content(file_key: str, txns: list[Transaction]) -> str:
    """Return new content for a regular x transactions .beancount file.

    Return will order transactions according to nature of file represented
    by `file_key`.

    Parameters
    ----------
    file_key
        key of `utils.FILE_CONFIG` describing nature of file being
        composed.

    txns
        All regular transactions to be included to file. Transactions do
        not need to be any particular order.

    Returns
    -------
    str
        New content for overwritting a regular expected transactions
        .beancount file of nature described by `file_key`.

    Raises
    ------
    ValueError
        If created content would parse a different number of transactions
        to the number of transactions receieved.
    """
    if file_key not in VALID_FILE_KEYS:
        valid_keys = ", ".join(VALID_FILE_KEYS)
        raise ValueError(
            f"'{file_key}' is not a valid file key. Valid values for"
            f" `file_key` are {valid_keys}."
        )

    if file_key.endswith("def"):
        txns_content = compose_definitions_content(txns)
    else:
        txns.sort(key=data.entry_sortkey)
        txns_content = utils.compose_entries_content(txns)
    content = utils.compose_new_content(file_key, txns_content)

    new_entries, _, _ = parser.parse_string(content)
    new_txns = utils.extract_txns(new_entries)
    if len(new_txns) != len(txns):
        raise ValueError(
            f"Expected {len(txns)} transactions to be loaded from content"
            f", but loaded {len(new_txns)}."
        )
    return content


class Admin:
    """Administrator of regular expected transactions.

    Parameters
    ----------
    All parameters can be passed as either absolute paths or paths relative
    to the cwd. It is not necessary to include the. beancount extension.
    For example, "rx" would refer to the file 'rx.beancount' in the cwd.

    defs : str
        Path to .beancount file containing Regular Expected Transaction
        definitions as a listing of each rx txn's last unmodified entry.

    ledger : str
        Path to .beancount file containing regular expected transactions.

    ledger_main : str | None
        Path to the main .beancount ledger file. This will be the ledger
        that 'includes' the Regular Expected Transactions Ledger `ledger`.

        This argument is only required if `add_txns` will be called to
        add new Regular Expected Transactions to the `ledger`.

    Raises
    ------
    BeancountLoaderErrors
        If `ledger_main` loads with errors.
    """

    def __init__(self, defs: str, ledger: str, ledger_main: str | None = None):
        self.path_defs = utils.get_verified_path(defs, "rx_def")
        self._verify_payees_unique()

        self.path_ledger = utils.get_verified_path(ledger, "rx")

        self.path_ledger_main: Path | None
        if ledger_main is None:
            self.path_ledger_main = None
        else:
            self.path_ledger_main = utils.get_verified_path(ledger_main)
            if errors := self._get_main_ledger_errors():
                raise BeancountLoaderErrors(self.path_ledger_main, errors)
            else:
                self._stored_content: dict[Path, str] = {}
                for path in [self.path_ledger, self.path_defs]:
                    self._store_content(path)

    def _verify_payees_unique(self):
        """Raise error if rx txn payees are not unique.

        Payee uniqueness is case-INsensitive, i.e. "Rent" and "rent" are
        considered to be repeated payees, not unique.
        """
        txns = utils.get_unverified_txns(self.path_defs)
        payees = [txn.payee.lower() for txn in txns]
        if len((unique_payees := set(payees))) < len(payees):
            repeated_payees = [
                payee for payee in unique_payees if payees.count(payee) > 1
            ]
            msg = (
                "The payee of each regular expected transaction must be unique"
                " (case insensitive) although the following payees are"
                f" repeated in the file {self.path_defs}:\n{repeated_payees}."
            )
            raise errors.RegularTransactionsDefinitionError(msg)

    @functools.cached_property
    def rx_defs(self) -> dict[str, Transaction]:
        """Last transaction of each Regular Expected Transaction.

        Returns
        -------
        dict
            key: str
                Regular Expected Transaction payee.

            value: Transaction
                Unmodified version of last entry injected for each regular
                transaction. This will be the transactions as defined on the
                reg_txn definitions file passed to the constructor.
        """
        txns = utils.get_unverified_txns(self.path_defs)
        return {txn.payee: txn for txn in txns}

    @property
    def payees(self) -> list[str]:
        """Payees defined Regular Expected Transactions."""
        return list(self.rx_defs.keys())

    @property
    def rx_files(self) -> tuple[Path]:
        """Paths of Regular Expected Transactions beancount files.

        Returns
        -------
        2-tuple of Path
            [0] Path to regular transactions definitions file.
            [1] Path to regular transactions ledger file.
        """
        return [self.path_defs, self.path_ledger]

    def _store_content(self, path: Path):
        """Store current content of a Regular Expected Transactions file.

        Parameters
        ----------
        path
            Path to rx txns file with contents to be stored.
        """
        assert path in self.rx_files
        self._stored_content[path] = utils.get_content(path)

    def _revert_to_stored_content(self, path: Path):
        """Revert a rx txns file to stored content."""
        stored_content = self._stored_content[path]
        utils.write(path, stored_content)

    def _get_main_ledger_errors(self) -> list[tuple]:
        """Errors registered on loading the main ledger.

        Returns
        -------
        list of tuple
            List of beancount errors registered on loading the main
            beancount ledger. Empty list indicates no errors.
        """
        entries, errors, options = loader.load_file(self.path_ledger_main)
        return errors

    def create_raw_new_entries(
        self, end: pd.Timestamp
    ) -> tuple[list[Transaction], list[Transaction]]:
        """Create new entries and defs for all regular expected txns.

        Parameters
        ----------
        end : pd.Timestamp
            Date to which to create Regular Expected Transactions.

        Returns
        -------
        2-tuple of list of Transaction
            [0] List of new entries.
            [1] List of new definitions.
        """
        entries, new_defs = [], []
        for rx_def in self.rx_defs.values():
            txns, new_def = create_entries(rx_def, end)
            entries += txns
            new_def = new_def if new_def is not None else rx_def
            new_defs.append(new_def)
        return entries, new_defs

    def _get_new_txns_data(
        self,
        end: pd.Timestamp,
    ) -> tuple[list[Transaction], list[Transaction]]:
        """Get data with which to update ledger with new entries.

        Parameters
        ----------
        end : pd.Timestamp
            Date to which to create new Regular Expected Transactions.

        Returns
        -------
        2-tuple of lists of Transaction
            [0] New entries to inject to Regular Expected Transactions Ledger.
            [1] Updated rx txns definitions based on new entries ([0]).
        """
        raw_entries, new_defs = self.create_raw_new_entries(end)
        new_entries = remove_after_final(raw_entries)
        new_defs = remove_after_final(new_defs)
        new_entries = roll_txns(new_entries)
        return new_entries, new_defs

    @property
    def rx_txns(self) -> list[Transaction]:
        """Regular Expected Transactions.

        Regular Expected Transactions as defined on the Regular Expected
        Transactions Ledger.
        """
        return utils.get_unverified_txns(self.path_ledger)

    def _validate_main_ledger(self, paths: list[Path]):
        """Validate main ledger loads without errors.

        If main ledger loads with errors then reverts content of `paths`
        and raises a RegularTransactionDefinitionError. Otherwise updates
        `paths` saved content to the current content.
        """
        if self.path_ledger_main is None:
            raise ValueError(
                "Main ledger cannot be validated as the path to the main ledger"
                "is unknown."
            )

        if not (errors_ := self._get_main_ledger_errors()):
            for path in paths:
                self._store_content(path)
            if self.path_defs in paths:
                # delete cache, will recache if/when called
                del self.rx_defs
            return

        else:
            for path in paths:
                self._revert_to_stored_content(path)
            raise errors.RegularTransactionsDefinitionError(
                "Changes resulted in the main ledger loading with the following errors:"
                f"\n{errors_}\n.The following files have been reverted to their prior"
                f" content:\n{paths}"
            )

    def _overwrite_beancount_file(
        self,
        path: Path,
        content: str,
        also_revert: list[Path] | None = None,
    ):
        """Overwrite contents of a regular expected transactions file.

        If an error is raised whilst attempting to overwrite then the file
        represented by `path` and any files represented by paths of
        `also_revert` will be reverted to their most recent stored content.

        Parameters
        ----------
        path
            Path to file to be overwritten.

        content
            Content to write to file at `path`.

        also_revert
            Paths to other files to revert

        Raises
        ------
        BeanaheadOverwriteError
            If any error is raised when overwritting the file.
        """
        try:
            utils.overwrite_file(path, content)
        except Exception as err:
            revert_paths = [path]
            if also_revert is not None:
                revert_paths.extend(also_revert)
            for path_ in revert_paths:
                self._revert_to_stored_content(path_)
            raise BeanaheadWriteError(path, revert_paths) from err

    def add_txns(self, end: str | pd.Timestamp = END_DFLT):
        """Add Regular Expected Transactions.

        Adds Regular Expected Transactions to the Regular Expected
        Transaction Ledger.

        Updates Regular Expected Transaction Definitions file so that each
        Regular Expected Transaction is defined by the (unmodified)
        'latest' rx txn to be added to the Regular Expected Transaction
        Ledger.

        Either transactions are added or an error is raised an no changes
        are made.

        Parameters
        ----------
        end : datetime.date | str | None, default: `END_DFLT`
            Date to which to add new Regular Expected Transactions to the
            ledger. Default is 13 weeks ahead of today.

            If passed as string then string should be in iso format, for
            exmaple "2022-09-18".
        """
        if self.path_ledger_main is None:
            raise ValueError(
                "New transactions cannot be added to the Regular Expected Transactions"
                " Ledger as the main ledger is not available (the main ledger is"
                " required in order to validate the new transactions). To use"
                " `add_txns`, pass the 'ledger_main' argument to the constructor."
            )

        if not isinstance(end, datetime.date):
            end = datetime.date.fromisoformat(end)

        new_txns, new_defs = self._get_new_txns_data(end)
        if not new_txns:
            print(f"There are no new Regular Expected Transactions to add with {end=}.")
            return

        ledger_txns = self.rx_txns + new_txns

        # ensure all new content checks out before writting anything
        content_ledger = compose_new_content("rx", ledger_txns)
        content_defs = compose_new_content("rx_def", new_defs)

        self._overwrite_beancount_file(self.path_ledger, content_ledger)
        also_revert = [self.path_ledger]
        self._overwrite_beancount_file(self.path_defs, content_defs, also_revert)
        self._validate_main_ledger(self.rx_files)
        print(
            f"{len(new_txns)} transactions have been added to the ledger"
            f" '{self.path_ledger.stem}'.\nDefinitions on '{self.path_defs.stem}' have"
            f" been updated to reflect the most recent transactions."
        )
