"""Functions to reconcile new transactions with expected transactions."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
import re

import beancount
from beancount import loader
from beancount.core import data
from beancount.core.data import Transaction
from beancount.core.getters import get_entry_accounts
from beancount.core import number
from beancount.ingest.extract import HEADER

from . import utils
from .errors import BeanaheadWriteError
from .utils import ENCODING


def load_extraction_file(path: Path) -> data.Entries:
    """Load entries extracted from statements.

    Parameters
    ----------
    path
        Path to extraction file.
    """
    # load from string in case need to accommodate lost balance directives...
    with path.open("rt", encoding=ENCODING) as file:
        string = file.read()

    # NB do not pass "utf-8" encoding to load_string. utf-8 is the default,
    # although does not encode as utf-8 if pass encoding!?
    new_entries, errors, options = loader.load_string(string)

    balance_errors = []
    for error in errors:
        if (
            isinstance(error, beancount.ops.balance.BalanceError)
            and error.message.startswith("Account ")
            and "does not exist" in error.message
        ):
            balance_errors.append(error)

    if balance_errors:
        # when these errors are 'raised' the associated balance directive is not
        # loaded. The following adds lines to create open directives for these
        # accounts and reloads the entries.
        for error in balance_errors:
            account = error.entry.account
            string += "1900-01-01 open " + account + "\n"
        new_entries_, errors, options = loader.load_string(string)
        # then removes the Open directives and loses balance diff from Balance
        # directives - not useful for an extraction file.
        new_entries = []
        for entry in new_entries_:
            if isinstance(entry, data.Open):
                continue
            if isinstance(entry, data.Balance):
                entry = entry._replace(diff_amount=None)
            new_entries.append(entry)

    return new_entries


def separate_out_txns(entries: data.Entries) -> tuple[list[Transaction], data.Entries]:
    """Separate transactions from other entries."""
    txns, others = [], []
    for entry in entries:
        lst = txns if isinstance(entry, Transaction) else others
        lst.append(entry)
    return txns, others


def get_close_txns(
    txns: list[Transaction], x_txn: Transaction, delta: timedelta
) -> list[Transaction]:
    """Return txns that are close to the date of an Expected Transaction.

    Parameters
    ----------
    txns
        Transactions from which to return those that are within `delta`
        from the date of `x_txn`.

    x_txn
        Expected Transaction to query.

    delta
        Delta, in days, that defines how close the date of a txn (of
        `txns`) should be to the date of the `x_txn` in order to be
        included in return.
    """
    start, end = x_txn.date - delta, x_txn.date + delta + timedelta(1)
    return list(data.iter_entry_dates(txns, start, end))


def bal_sheet_accounts_match(a: Transaction, b: Transaction) -> bool:
    """Query if two transactions have postings to same bal sheet acc."""
    accounts_a = utils.get_balance_sheet_accounts(a)
    accounts_b = utils.get_balance_sheet_accounts(b)
    return bool(set(accounts_a).intersection(set(accounts_b)))


def get_accounts_matches(
    txns: list[Transaction], x_txn: Transaction
) -> list[Transaction]:
    """Return txns matching an Expected Transaction's bal sheet acc.

    Returns
    -------
    list of Transaction
        Transactions of `txns` with a posting to a balance sheet account
        to which the `x_txn` also has a posting.
    """
    return [txn for txn in txns if bal_sheet_accounts_match(txn, x_txn)]


def get_basic_matches(txns: list[Transaction], x_txn: Transaction) -> list[Transaction]:
    """Return transactions that basically match an Expected Transaction.

    Returns
    -------
    list of Transaction
        Transactions of `txns` that match `x_txn` based on:
            Closeness of dates (5 days)
            Postings to same balance sheet account.
    """
    matches = get_close_txns(txns, x_txn, timedelta(days=5))
    return get_accounts_matches(matches, x_txn)


def get_pattern(x_txn: Transaction) -> re.Pattern:
    """Get a pattern to match an Expected Transaction's payee"""
    payee = x_txn.payee
    words = payee.split(" ")
    if len(words) == 1:
        return re.compile(payee, re.I)
    return utils.compile_strings_regex(words)


def get_payee_matches(txns: list[Transaction], x_txn: Transaction) -> list[Transaction]:
    """Return transactions matching an Expected Transaction's payee."""
    pattern = get_pattern(x_txn)
    return [txn for txn in txns if pattern.search(txn.payee) is not None]


def get_common_accounts(a: Transaction, b: Transaction) -> set[str]:
    """Return set of accounts that are common to two transactions."""
    return get_entry_accounts(a).intersection(get_entry_accounts(b))


def get_common_balance_sheet_accounts(a: Transaction, b: Transaction) -> set[str]:
    """Return set of balance sheet accounts common to two transactions."""
    common_accounts = get_common_accounts(a, b)
    return {acc for acc in common_accounts if utils.is_balance_sheet_account(acc)}


def get_posting_to_account(txn: Transaction, account: str) -> data.Posting | None:
    """Return a transaction's posting to a given account

    None if transaction does not have a posting to `account`.
    """
    postings = [post for post in txn.postings if post.account == account]
    if len(postings) > 1:
        raise ValueError(
            "Transaction cannot have multiple postings to the same account"
            " although the following transaction has multiple postings to"
            f" '{account}':\n{txn}"
        )
    if not postings:
        return None
    return postings[0]


def get_amount_for_account(txn: Transaction, account: str) -> data.Amount | None:
    """Return amount of a transaction's posting to a given account.

    Returns None if no posting to `account`.
    """
    posting = get_posting_to_account(txn, account)
    return None if posting is None else posting.units


def decimal_diff(a: Decimal, b: Decimal) -> Decimal:
    """Return difference of a decimal relative to another.

    Returns
    -------
    Decimal
        Decimal bewteen 0 and 1 representing percentage difference of
        larger number relative to smaller number.

        Decimal(1) if the signs of `a` and `b` are different.

    Examples
    --------
    >>> decimal_diff(Decimal("40"), Decimal("40"))
    Decimal('0')
    >>> decimal_diff(Decimal("40"), Decimal("50"))
    Decimal('0.2')
    >>> decimal_diff(Decimal("50"), Decimal("40"))
    Decimal('0.2')
    >>> decimal_diff(Decimal("-50"), Decimal("-40"))
    Decimal('0.2')
    >>> decimal_diff(Decimal("-50"), Decimal("40"))
    Decimal('1')
    """
    if a * b < number.ZERO:
        return number.ONE
    denom = max(abs(a), abs(b))
    return abs(a - b) / denom


def number_diff(a: Transaction, b: Transaction) -> Decimal:
    """Return percentage difference between number of two transactions.

    Return represents percentage difference of number(s) of `b` from `a`.

    Returns
    -------
    Decimal
        Decimal bewteen 0 and 1 representing average percentage difference
        between transactions' postings' 'number' (only for postings
        to balance sheet accounts that are common to both transactions).
        Decimal(0) indicates the number of postings' to all common balance
        sheet accounts are exactly the same.

        Returns Decimal(1) if
            There are no common balance sheet accounts with number
            denominated in same currency.

            For a common balance sheet account the sign of the number on
            each transaction is different.
    """
    diffs = []
    for account in get_common_balance_sheet_accounts(a, b):
        num_a, cur_a = get_amount_for_account(a, account)
        num_b, cur_b = get_amount_for_account(b, account)
        if not cur_a == cur_b:
            continue
        diff = decimal_diff(num_a, num_b)
        if diff == number.ONE:
            return diff
        diffs.append(diff)
    if not diffs:
        return number.ONE
    return abs(sum(diffs) / len(diffs))


def get_sortkey_number(x_txn: Transaction) -> Callable:
    """Get sortkey function to sort transactions by difference in number.

    Sortkey function will sort transactions by difference in number to
    `x_txn`.
    """

    def sortkey_number(txn: Transaction) -> Decimal:
        """sortkey to sort transactions by difference in number."""
        return number_diff(x_txn, txn)

    return sortkey_number


def sort_by_number(txns: list[Transaction], x_txn: Transaction) -> list[Transaction]:
    """Sort transactions by difference in number with Expected Transaction.

    Returns sorted copy of transactions.
    """
    return sorted(txns, key=get_sortkey_number(x_txn))


def get_sortkey_date(x_txn: Transaction) -> Callable:
    """Get sortkey function to sort transactions by difference in dates.

    Sortkey function will sort transactions by, in order of priority:
        difference in date with `x_txn`.
        number of common accounts.
    """

    def sortkey_date(txn: Transaction) -> Decimal:
        """sortkey to sort transactions by difference in date."""
        return (abs(x_txn.date - txn.date), -len(get_common_accounts(txn, x_txn)))

    return sortkey_date


def sort_by_date(txns: list[Transaction], x_txn: Transaction) -> list[Transaction]:
    """Sort transactions by difference in date with an expected transaction.

    Returns sorted copy of transactions.
    """
    return sorted(txns, key=get_sortkey_date(x_txn))


def have_same_number(a: Transaction, b: Transaction) -> bool:
    """Query if two transactions' postings to common accounts have same number."""
    return number_diff(a, b) == number.ZERO


def get_number_matches(
    txns: list[Transaction], x_txn: Transaction, margin: Decimal = number.ZERO
) -> list[Transaction]:
    """Return transactions matching expected transaction's numbers."""
    return [txn for txn in txns if number_diff(x_txn, txn) <= margin]


def get_matches(txns: list[Transaction], x_txn: Transaction) -> list[Transaction]:
    """Match an Expected Transaction to one or more incoming transactions."""
    basic_matches = get_basic_matches(txns, x_txn)
    if not basic_matches:
        return []

    payee_matches = get_payee_matches(basic_matches, x_txn)
    if not payee_matches:
        # if no matches by payee then return only those within 2%
        matches = get_number_matches(basic_matches, x_txn, Decimal("0.02"))
        return sort_by_date(matches, x_txn)
    if len(payee_matches) == 1:
        return payee_matches

    matches = sort_by_date(payee_matches, x_txn)
    closest_match = matches[0]
    # if closest match has exact value, return only those with that date and exact value
    if have_same_number(closest_match, x_txn):
        delta = abs(closest_match.date - x_txn.date)
        return [
            txn
            for txn in matches
            if abs(txn.date - x_txn.date) == delta and have_same_number(txn, x_txn)
        ]
    return sort_by_number(matches, x_txn)


MSG_SINGLE_MATCH = "Do you want to match the above transactions? y/n: "


def confirm_single(
    x_txn: Transaction, matches: list[Transaction]
) -> Transaction | None:
    """Get user to decide if two transactions should be matched.

    Parameters
    ----------
    x_txn
        Expected transaction

    matches
        List of length 1 containing incoming match.

    Returns
    -------
    pd.Transaction or None
        Matched transaction, if user confirm match.
        None if user rejects match.
    """
    print(
        f"{utils.SEPARATOR_LINE}Expected Transaction:\n"
        f"{utils.compose_entries_content(x_txn)}\n"
        f"Incoming Transaction:\n{utils.compose_entries_content(matches[0])}"
    )
    response = utils.get_input(MSG_SINGLE_MATCH).lower()
    while response not in ["n", "y"]:
        response = utils.get_input(
            f"{response} is not valid input, please try again, y/n: "
        )
    if response == "n":
        return None
    elif response == "y":
        return matches[0]


def get_mult_match(
    x_txn: Transaction, matches: list[Transaction]
) -> Transaction | None:
    """Get user to choose a match from various options.

    Requests user decides which of `matches` to match with `x_txn`, or to
    reject all matches.

    Returns
    -------
    pd.Transaction or None
        Matched transaction, as choosen by user.
        None if user rejects all matches.
    """
    print(
        f"{utils.SEPARATOR_LINE}Expected Transaction:\n"
        f"{utils.compose_entries_content(x_txn)}\n\n"
        f"Incoming Transactions:\n"
    )
    for i, match in enumerate(matches):
        print(f"{i}\n{utils.compose_entries_content(match)}")

    max_value = len(matches) - 1
    options = f"[0-{max_value}]/n"
    response = utils.get_input(
        "Which of the above incoming transactions do you wish to match"
        f" with the expected transaction, or 'n' for None, {options}:"
    )
    while not (
        (response == "n") or utils.response_is_valid_number(response, max_value)
    ):
        response = utils.get_input(
            f"{response} is not valid input, please try again {options}: "
        )
    if response == "n":
        return None
    return matches[int(response)]


def reconcile_x_txns(
    x_txns: list[Transaction], new_txns: list[Transaction]
) -> list[tuple[Transaction, Transaction]]:
    """Reconcile Expected Transactions with new transactions.

    Requests user confirm or decide matches.

    Parameters
    ----------
    x_txns
        Expected Transactions to be reconciled.

    new_txns
        Incoming transactions to reconile Expected Transactions against.

    Returns
    -------
    list of 2-tuple of Transaction
        Each 2-tuple represents a match, where
            [0] Expected Transaction
            [1] new transaction matched with [0]
        Only matched Expected Transactions, of `x_txns`, are inlcuded in
        return.
    """
    reconciled = []
    new_txns = new_txns.copy()
    for x_txn in x_txns:
        matches = get_matches(new_txns, x_txn)
        if not matches:
            continue
        match_func = confirm_single if len(matches) == 1 else get_mult_match
        match = match_func(x_txn, matches)
        if match is not None:
            reconciled.append((x_txn, match))
            new_txns.remove(match)
    return reconciled


def update_new_txn(new_txn: Transaction, x_txn: Transaction) -> Transaction:
    """Update a incoming txn with data from a matched Expected Transaction.

    The following fields of the `new_txn` will be updated with the
    corresponding fields of `x_txn`:
        narration
        tags (excluding expected transaction tags, for example #rx_txn)
        meta:
            Items of `x_txn` meta will be added to the `new_txn` meta if
            the key is not already present. This excludes beanahead meta
            fields ('final', 'roll' etc) which will not be added to the
            `new_txn`.
        postings:
            postings to the `x_txn` will be added to the `new_txn` posting
            if the `new_txn` does not otherwise include a posting to the
            corresponding account.

            If the `new_txn` and `x_txn` include postings to the same
            account and only the `x_txn` defines a number, the posting to
            the `new_txn` will be updated to reflect the value as defined
            on the `x_txn`

    All other fields ('date', 'payee' etc), will remain as defined on the
    `new_txn`.

    Parameters
    ----------
    new_txn
        Incoming transaction matched with `x_txn`.

    x_txn
        Expected transaction matched with `new_txn`.

    Returns
    -------
    Transaction
        Copy of `new_txn` updated to reflect any complementary data
        provided by `x_txn`.

    Notes
    -----
    For the purpose of evaluating which postings should be updated,
    postings are treated as defined on underlying ledger from which data
    loaded - i.e. any numbers that are interpolated on loading are ignored.
    """
    # reverse_automatic_balancing returns copies
    x_txn = utils.reverse_automatic_balancing(x_txn)
    new_txn = utils.reverse_automatic_balancing(new_txn)

    if not new_txn.narration:
        new_txn = new_txn._replace(narration=x_txn.narration)

    if tags_to_add := x_txn.tags - utils.TAGS_X:
        new_txn = utils.add_tags(new_txn, tags_to_add)

    new_txn = new_txn._replace(meta=new_txn.meta.copy())
    for k, v in x_txn.meta.items():
        if k in utils.RX_META_DFLTS or k in new_txn.meta or k == "freq":
            continue
        new_txn.meta[k] = v

    new_txn_accounts = get_entry_accounts(new_txn)
    for posting in x_txn.postings:
        if (account := posting.account) not in new_txn_accounts:
            new_txn.postings.append(posting)
        else:
            new_txn_posting = get_posting_to_account(new_txn, account)

            # carry over any meta not otherwise defined on new_txn
            updated_posting = new_txn_posting._replace(meta=new_txn_posting.meta.copy())
            for k, v in posting.meta.items():
                updated_posting.meta.setdefault(k, v)

            if updated_posting.units is None:
                updated_posting = updated_posting._replace(units=posting.units)

            new_txn.postings.remove(new_txn_posting)
            new_txn.postings.append(updated_posting)
    return new_txn


def update_new_txns(
    new_txns: list[Transaction],
    reconciled_x_txns: list[tuple[Transaction, Transaction]],
) -> list[Transaction]:
    """Update incoming transactions for matched data.

    Parameters
    ----------
    new_txns
        Incoming transactions (from injection file).

    reconciled_x_txns : list of 2-tuple of Transaction
        Where each 2-tuple represents a matched expected transaction:
            [0] expected transaction
            [1] new txn, of `new_txns`, matched with [0]

    Returns
    -------
    list of Transaction
        `new_txns` as updated. Received order is NOT maintained.
    """
    for x_txn, new_txn in reconciled_x_txns:
        updated_txn = update_new_txn(new_txn, x_txn)
        new_txns.insert(0, updated_txn)
        new_txns.remove(new_txn)
    return new_txns


def map_path_to_reconciled_x_txns(
    x_txns: dict[Path, list[Transaction]],
    reconciled_x_txns: tuple[Transaction, Transaction],
) -> dict[Path, list[Transaction]]:
    """Map reconciled x_txns to ledgers they were defined on.

    Parameters
    ----------
    x_txns : dict
        key : Path
            Path to ledger on which 'value' defined.
        value : list of Transaction
            Expected Transactions defined on 'key'.

    reconciled_x_txns : 2-tuple of Transaction
        As return from reconcile_x_txns() function.

    Returns
    -------
    dict
        key: Path
            Path to ledger on which 'value' defined.
        value: list of Transaction
            Reconciled Expected Transactions defined on 'key'.
    """
    mapping = defaultdict(list)
    for x_txn, _ in reconciled_x_txns:
        mapped = False
        for path, txns in x_txns.items():
            if x_txn in txns:
                mapping[path].append(x_txn)
                mapped = True
                break
        assert mapped, "reconciled x_txn not mapped to path."
    return mapping


def reconcile_new_txns(
    new_entries: str,
    x_txns_ledgers: list[str],
    remove: bool = True,
    output: str | None = None,
    ascending: bool = True,
):
    """Reconcile new transactions with expected transactions.

        Evaluates potential matches between incoming and expected
        transactions.

        Requests user intervention to confirm potential matches
        and resolve ambiguities.

        Updates each matched incoming transaction with the following
        fields of the matched expected transaction:
            narration
            postings:
                postings to the x_txn will be added to the new_txn
                posting if the new_txn does not otherwise include a
                posting to the corresponding account.

                If the new_txn and x_txn include postings to the same
                account and only the x_txn defines a number, the posting
                to the 'new_txn' will be updated to reflect the value as
                defined on the 'x_txn'.

        Writes updated incoming transactions to output (by default
        overwrites `new_entries`).

        Optinally, removes matched expected transactions from the
        corrsponding expected transaction ledger by way of rewritting
        these ledgers with the remaining, unmatched, transactions.

    Parameters
    ----------
    Where a parameter takes one or more file addresses, the address can
    be defined as either absolute paths or paths relative to the cwd. It
    is not necessary to include the. beancount extension. For example,
    "rx" would refer to the file 'rx.beancount' in the cwd.

    new_entires : str
        Path to .beancount file containing incoming transactions and
        other new entries. Entries in file should represent ONLY new
        entries.

    x_txns_ledgers : list of str
        List of paths to expected transactions ledgers which list
        transactions that include transactions that may reconcile
        with one or more transactions of `new_txns`.

    remove : bool, default: True
        Should matched expected transactions be removed from the
        corresponding ledger of `x_txns_ledgers`. This has the effect
        rewritting the corresponding expected transaction ledger(s) with
        the remaining, unmatched, expected transactions. As part of this
        rewrite all entries are resorted in ascending order.

    output : str, default: overwrite file represented by `new_entries`
        Path to .beancount file to which the reconciled new entries
        should be written. Any existing file will be overwritten.

    ascending : bool, default: True
        True to order output earliest transfer first.
        False to order output latest transfer first.
    """
    input_path = utils.get_verified_path(new_entries)
    new_entries_ = load_extraction_file(input_path)
    new_txns, new_other = separate_out_txns(new_entries_)

    x_txns: dict[Path, list[Transaction]] = {}
    for ledger in x_txns_ledgers:
        path = utils.get_verified_path(ledger)
        _ = utils.get_verified_ledger_file_key(path)  # just verify that a ledger
        x_txns[path] = utils.get_unverified_txns(path)

    all_x_txns = []
    for txns in x_txns.values():
        all_x_txns.extend(txns)

    reconciled_x_txns = reconcile_x_txns(all_x_txns, new_txns)
    updated_new_txns = update_new_txns(new_txns, reconciled_x_txns)
    updated_entries = updated_new_txns + new_other
    updated_entries.sort(key=data.entry_sortkey, reverse=not ascending)

    out_path = input_path if output is None else utils.get_unverified_path(output)
    out_content = HEADER + "\n" + utils.compose_entries_content(updated_entries)

    x_txns_to_remove = (
        map_path_to_reconciled_x_txns(x_txns, reconciled_x_txns) if remove else {}
    )

    # Write / Overwrite files, reverting all to previous content on any errors
    prev_contents = {path: utils.get_content(path) for path in x_txns_to_remove}
    seen: list[Path] = []
    try:
        for path, txns in x_txns_to_remove.items():
            seen.append(path)
            utils.remove_txns_from_ledger(path, txns)
    except Exception as err:
        for revert_path in seen[:]:
            try:
                utils.write(revert_path, prev_contents[revert_path])
            except Exception:
                seen.remove(revert_path)
        raise BeanaheadWriteError(path, seen) from err

    overwrite = False
    if out_path.is_file():
        prev_contents[out_path] = utils.get_content(out_path)
        overwrite = True
    try:
        utils.write(out_path, out_content)
    except Exception as err:
        reverted = list(prev_contents.keys())
        for revert_path, prev_content in prev_contents.items():
            try:
                utils.write(revert_path, prev_content)
            except Exception:
                reverted.remove(revert_path)
        raise BeanaheadWriteError(out_path, reverted, overwrite) from err

    msg = (
        f"{len(reconciled_x_txns)} incoming transactions have been reconciled against"
        f" expected transactions.\nUpdated transactions have been output to"
        f" '{out_path}'."
    )
    for path, txns in x_txns_to_remove.items():
        msg += f"\n{len(txns)} transactions have been removed from ledger {path}."

    print(msg)
