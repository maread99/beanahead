"""Functions and class for administering regular transactions."""

from __future__ import annotations

import copy
from collections import defaultdict
import datetime
import functools
from pathlib import Path
from typing import Literal

import pandas as pd
from beancount import loader
from beancount.core import data
from beancount.core.data import Transaction
from beancount.core.account_types import get_account_type
from beancount.parser import parser
from beancount.parser.printer import EntryPrinter

from . import utils
from .errors import BeanaheadWriteError, BeancountLoaderErrors

# TODO TESTS FOR ALL OF MODULE!!!!

END_DFLT = utils.TODAY + datetime.timedelta(weeks=13)


def get_freq(txn: Transaction) -> pd.DateOffset:
    """Get frequency of a regular transaction.

    Parameters
    ----------
    txn
        Transaction to query.
    """
    return pd.DateOffset(**eval(txn.meta["freq"]))


def create_entries(
    rx_txn_def: Transaction,
    end: datetime.date,
) -> list[Transaction]:
    """Create entries for a regular transaction.

    Creates entries from last transaction to a future date.

    Parameters
    ----------
    rx_txn_def
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
    list of Transaction
        Transactions from `rx_txn_def` through end, exclusive of
        `rx_txn_def`. Transaction dates are as they fall based ONLY on the
        transaction frequency, i.e. transactions are NOT modified by, for
        example, rolling forwards over a weekend.
    """
    end = END_DFLT if end is None else end
    dates = pd.date_range(rx_txn_def.date, end, freq=get_freq(rx_txn_def))[1:]
    txns = []
    for date in dates:
        txn = copy.copy(rx_txn_def)
        txn = txn._replace(date=date.date())
        txns.append(txn)
    return txns


def roll_txns(txns: list[Transaction]) -> list[Transaction]:
    """Roll transactions that roll forwards at weekend.

    Any transaction that is set to roll and falls on a weekendis replaced
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


def convert_for_printer(txn: Transaction) -> Transaction:
    """Convert a regular transaction for printing to a .beancount file.

    Reverses any interpolation of numbers for missing fields.
    Removes meta fields that have default values.
    Removes reg_txn tag.

    Parameters
    ----------
    txn
        Transaction to convert.

    Returns
    -------
    Transaction
        Converted copy of `txn`.
    """
    txn = utils.reverse_automatic_balancing(txn)
    meta = copy.deepcopy(txn.meta)
    if meta["final"] is None:
        del meta["final"]
    if meta["roll"]:
        del meta["roll"]
    converted = txn._replace(meta=meta)
    converted = utils.remove_tags(converted, utils.TAG_RX)
    return converted


INCOME_STATEMENT_ACCOUNTS = ["Income", "Expenses"]
OTHER_SIDE_ACCOUNTS = {"Assets": 0, "Income": 1, "Expenses": 2}


def get_income_statement_acc_type(
    txn: Transaction,
) -> Literal["Income", "Expenses"]:
    """Return root of `income statement` account associated with a transaction.

    Parameters
    ----------
    txn
        Transaction to be queried.

    Raises
    ------
    ValueError
        If `txn` has no postings to an income statement account.

        If postings are made to more than one type of `income statement`
        account.
    """
    valid_account_types = []
    for posting in txn.postings:
        account_type = get_account_type(posting.account)
        if account_type in INCOME_STATEMENT_ACCOUNTS:
            valid_account_types.append(account_type)
    if not valid_account_types:
        raise ValueError(
            "Transaction has no posting to an income statement account"
            f" ('{INCOME_STATEMENT_ACCOUNTS}'):\n{txn}"
        )
    if len(account_type := set(valid_account_types)) != 1:
        raise ValueError(
            "Transaction has postings to both an 'Income' account"
            f" and an 'Expense' account:\n{txn}"
        )
    return account_type.pop()


GrouperKey = tuple[str, str]


def group_definitions(
    txns: list[Transaction],
) -> dict[GrouperKey, list[Transaction]]:
    """Group definitions by accounts.

    Groups definitions by assets account and 'other account'.

    Parameters
    ----------
    txns
        Transactions to be grouped.

    Returns
    -------
    dict
        key : 2-tuple of str, str
            [0] Assets account
            [1] Other account type (either 'Assets', 'Income' or 'Expenses'
            Example: ("Assets:US:Chase:Checking", "Expenses")

        value : list of Transaction
            List of transactions posted to accounts with key.
    """
    grouper = defaultdict(list)
    for txn in txns:
        assets_accounts = utils.get_assets_accounts(txn)
        assets_account = assets_accounts[0]
        if len(assets_accounts) > 1:
            other_side = "Assets"
        else:
            other_side = get_income_statement_acc_type(txn)
        key = (assets_account, other_side)
        grouper[key].append(txn)
    return grouper


def sortkey_grouper(grouper_key: GrouperKey) -> tuple[str, str]:
    """sortkey for a GrouperKey.

    Sorts by:
        Assets account name
        Other account name ("Assets", "Income", "Expenses")

    Parameters
    ----------
    grouper_key: tuple[str, str]
        [0] An assets account.
        [1] Type of other account, i.e. "Assets", "Income" or "Expenses".
    """
    return (grouper_key[0], OTHER_SIDE_ACCOUNTS[grouper_key[1]])


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
        asset_acc, other_acc = key
        content += f"* {asset_acc} to {other_acc}\n"
        group_txns = grouper[key]
        group_txns.sort(key=lambda txn: txn.meta["name"])
        for txn in group_txns:
            txn = utils.reverse_automatic_balancing(txn)
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

    txns = [convert_for_printer(txn) for txn in txns]
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


class RegularTransactionsDefinitionError(Exception):
    """Error in a regular transactions definition file"""


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
        self._verify_names_unique()

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

    @functools.cached_property
    def rx_txn_defs(self) -> dict[str, Transaction]:
        """Last transaction of each Regular Expected Ttransaction.

        Returns
        -------
        dict
            key: str
                Regular Expected Transaction name.

            value: Transaction
                Unmodified version of last entry injected for each regular
                transaction. This will be the transactions as defined on the
                reg_txn definitions file passed to the constructor.
        """
        txns = utils.get_unverified_txns(self.path_defs)
        return {txn.meta["name"]: txn for txn in txns}

    @property
    def names(self) -> list[str]:
        """Names of defined Regular Expected Transactions."""
        return list(self.rx_txn_defs.keys())

    def _verify_names_unique(self):
        """Raise error if rx txn names are not unique.

        Name uniqueness is case-INsensitive, i.e. "Rent" and "rent" are
        considered to be repeated names, not unique.
        """
        names = [name.lower() for name in self.names]
        if len((unique_names := set(names))) < len(names):
            repeated_names = [name for name in unique_names if names.count(name) > 1]
            msg = (
                "The names of each regular expected transaction must be unique"
                " (case insensitive) although the following name(s) are"
                f" repeated in the file {self.path_defs}:\n{repeated_names}."
            )
            raise RegularTransactionsDefinitionError(msg)

    @property
    def rx_txns_files(self) -> tuple[Path]:
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
        assert path in self.rx_txns_files
        self._stored_content[path] = utils.get_content(path)

    def _revert_to_stored_content(self, path: Path):
        """Revert a rx txns file to stored content."""
        stored_content = self._stored_content[path]
        with path.open("wt") as file:
            file.write(stored_content)

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

    def create_raw_new_entries(self, end: pd.Timestamp) -> list[Transaction]:
        """Create new entries for all Regular Expected Transactions.

        Parameters
        ----------
        end : pd.Timestamp
            Date to which to create Regular Expected Transactions.

        Returns
        -------
        list of Transaction
            List of new entries.
        """
        entries = []
        for reg_txn_def in self.rx_txn_defs.values():
            txns = create_entries(reg_txn_def, end)
            entries += txns if txns else []
        return entries

    def _map_name_to_txns(
        self, txns: list[Transaction]
    ) -> dict[str, list[Transaction]]:
        """Return mapping of all names to Regular Expected Transactions.

        Parameters
        -------
        txns
            Transactions to be mapped.

        Returns
        -------
        dict
            key: str
                Regular Expected Transaction name
            value: list[Transaction]
                List of transactions with name as key. List will be in same
                order as received `txns`. List will be empty if `txns` contains
                no transactions for the Regular Expected Transaction.
        """
        d = {name: [] for name in self.names}
        for txn in txns:
            d[txn.meta["name"]].append(txn)
        return d

    def _get_new_defs(self, new_entries: list[Transaction]) -> list[Transaction]:
        """Return list of new definitions for each rx txn.

        Parameters
        ----------
        new_entries
            List of unmodified new entries to be added (post modifiaction)
            to the Regular Expected Transactions Ledger.

        Return
        ------
        list of Transaction
            List of new Regular Expected Transaction definitions. List
            contains last transaction for every tx txn. For rx txns
            that a new transaction is not included to `new_entries`, the
            definition will be as the existing.
        """
        mapping = self._map_name_to_txns(new_entries)
        new_defs = []
        for name, txns in mapping.items():
            if not txns:
                new_def = self.rx_txn_defs[name]
            else:
                new_def = txns[-1]
                assert max(txn.date for txn in txns) == new_def.date
            new_defs.append(new_def)
        assert len(self.names) == len(new_defs)
        return new_defs

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
        raw_entries = self.create_raw_new_entries(end)
        new_defs = self._get_new_defs(raw_entries)
        new_entries = roll_txns(raw_entries)
        return new_entries, new_defs

    @property
    def rx_txns(self) -> list[Transaction]:
        """Regular Expected Transactions.

        Regular Expected Transactions as defined on the Regular Expected
        Transactions Ledger.
        """
        return utils.get_unverified_txns(self.path_ledger)

    @property
    def rx_txns_expired(self) -> list[Transaction]:
        """Get Regular Expected Transactions dated prior to today."""
        return utils.get_expired_txns(self.rx_txns)

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

        if not (errors := self._get_main_ledger_errors()):
            for path in paths:
                self._store_content(path)
            if self.path_defs in paths:
                # delete cache, will recache if/when called
                del self.rx_txn_defs
            return

        else:
            for path in paths:
                self._revert_to_stored_content(path)
            raise RegularTransactionsDefinitionError(
                "Changes resulted in the main ledger loading with the following errors:"
                f"\n{errors}\n.The following files have been reverted to their prior"
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
            for path in revert_paths:
                self._revert_to_stored_content(path)
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
        self._validate_main_ledger(self.rx_txns_files)
        print(
            f"{len(new_txns)} transactions have been added to the ledger"
            f" '{self.path_ledger.stem}'.\nDefinitions on '{self.path_defs.stem}' have"
            f" been updated to reflect the most recent transactions."
        )
