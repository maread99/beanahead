"""Functions to administer expired transactions."""

from __future__ import annotations

import datetime
from datetime import timedelta
from pathlib import Path
import re

from beancount.core.data import Transaction

from . import utils
from .errors import BeanaheadWriteError

TODAY = utils.TODAY
TOMORROW = TODAY + timedelta(1)

DATE_FORMATS = "(YYYY-MM-DD or MM-DD or DD)"
VALID_DATE_FORMAT_REGEXES = [
    re.compile(r"^\d{4}-\d{1,2}-\d{1,2}$"),
    re.compile(r"^\d{1,2}-\d{1,2}$"),
    re.compile(r"^\d{1,2}$"),
]


def is_valid_date_format(string: str) -> bool:
    """Query if a string is in valid date format.

    Examples
    --------
    >>> is_valid_date_format("2022-08-15")
    True
    >>> is_valid_date_format("2022-8-15")
    True
    >>> is_valid_date_format("08-15")
    True
    >>> is_valid_date_format("15-08")  # NB Not a valid date, but a valid date format
    True
    >>> is_valid_date_format("15")
    True
    >>> is_valid_date_format("22-08-15")
    False
    >>> is_valid_date_format("2022")
    False
    >>> is_valid_date_format("08-15-2022")
    False
    >>> is_valid_date_format("08-15-22")
    False
    """
    return any(regex.match(string) is not None for regex in VALID_DATE_FORMAT_REGEXES)


def _get_date_parts(response: str) -> tuple[int, int, int]:
    """Return parts of date to be formed from user response.

    If response does not define a month then month will be returned
    as the current month or the next month depending on whether the
    defined day is, respectively, >= or < the current day.

    If response does not define a year then year will be returned as
    the current year or the next year, depending on whether the defined
    or eveluated month/day combination represent a day, respectively,
    >= or < the current day.

    Parameters
    ----------
    response
        User response to request for date. `response` must match
        a regex of `valid_date_format_regexes`
    """
    parts = [int(part) for part in response.split("-")]
    day = parts[-1]
    if len(parts) == 3:
        year, month = parts[0:2]
    else:
        if len(parts) == 2:
            month = parts[0]
        elif day >= TODAY.day:
            month = TODAY.month
        else:
            month = 1 if TODAY.month + 1 == 13 else TODAY.month + 1

        if month == TODAY.month:
            year = TODAY.year if day >= TODAY.day else TODAY.year + 1
        else:
            year = TODAY.year if month > TODAY.month else TODAY.year + 1
    return year, month, day


def _get_date_from_response(response: str) -> datetime.date | None:
    """Get date corresponding with user input.

    Returns
    -------
    datetime.date or None
        datetime.date representing `response`.
        None if `response` does not represent a valid date.
    """
    if not is_valid_date_format(response):
        return None
    parts = _get_date_parts(response)
    try:
        return datetime.date(*parts)
    except ValueError:
        return None


def _update_txn(txn: Transaction, path: Path) -> Transaction | None:
    """Return updated expired transaction according to user response.

    Parameters
    ----------
    txn
        Expired expected transaction to update.

    path
        Path to ledger on which txn defined.

    Returns
    -------
    Transaction
        Existing `txn` if user chooses to leave 'as is'.
        None if user choose to remove.
        Otherwise a new Transaction object with revised date.
    """
    print(
        f"{utils.SEPARATOR_LINE}\nThe following transaction has expired."
        f"\n\n{utils.compose_entries_content(txn)}"
        f"\n0 Move transaction forwards to tomorrow ({TOMORROW})."
        f"\n1 Move transaction forwards to another date."
        f"\n2 Remove transaction from ledger {path.stem}."
        f"\n3 Leave transaction as is."
    )
    response: str = utils.get_input("Choose one of the above options, [0-3]:")
    while not utils.response_is_valid_number(response, 3):
        response = utils.get_input(
            f"'{response}' is not valid input, please try again, [0-3]: "
        )
    if response == "3":
        return txn
    elif response == "2":
        return None
    elif response[0] == "0":
        return txn._replace(date=TOMORROW)

    response = utils.get_input(f"Enter a new date {DATE_FORMATS}: ")
    while (date := _get_date_from_response(response)) is None or (date < TODAY):
        if date is None:
            response = utils.get_input(
                f"'{response}' does not represent a valid date."
                f"\nPlease enter a valid date {DATE_FORMATS}: "
            )
        else:
            response = utils.get_input(
                f"'{response}' does not represent a date >= {TODAY}."
                f"\nPlease enter a valid date {DATE_FORMATS}: "
            )
    return txn._replace(date=date)


def overwrite_ledgers(contents: dict[Path, str]):
    """Write content to expected transaction ledgers.

    If an error is raised during the writing process then:
        Attempts to revert all overwritten ledgers to prior content.

        Raises BeanaheadWriteError advising which ledgers were
        reverted.

    Parameters
    ----------
    contents : dict
        key : Path
            Path of ledger to which to write 'value'.
        value: str
            Content to write to 'key'.

    Raises
    ------
    BeanaheadWriteError
        If any error is raised during any write process.
    """
    prev_contents = {path: utils.get_content(path) for path in contents}
    seen = []
    try:
        for path, content in contents.items():
            seen.append(path)
            utils.overwrite_file(path, content)
    except Exception as err:
        for path_ in seen[:]:
            try:
                utils.write(path_, prev_contents[path_])
            except Exception:
                seen.remove(path_)
        raise BeanaheadWriteError(path, seen) from err


def admin_expired_txns(ledgers: list[str]):
    """Administer expired expected transactions.

    For each expired transaction on a ledger of `ledgers`:
        Requests user choose from following options:
            Move txn forwards to tomorrow.
            Move txn forwards to user-defined date.
            Remove transaction from ledger.
            Leave transaction as is.

        Actions request.

    Ledgers on which at least one transaction is moved forward or removed
    will be rewritten. As part of this all remaining entries are sorted
    in ascending order.

    Parameters
    ----------
    ledgers
        List of paths to expected transactions ledgers. Paths can
        be defined as absolute or relative to the cwd. It is not
        necessary to include the. beancount extension. For example,
        "rx" would refer to the file 'rx.beancount' in the cwd.
    """
    x_txns: dict[Path, list[Transaction]] = {}
    file_keys: dict[Path, str] = {}
    for ledger in ledgers:
        path = utils.get_verified_path(ledger)
        file_keys[path] = utils.get_verified_ledger_file_key(path)
        x_txns[path] = utils.get_unverified_txns(path)

    no_expired_txns = True
    paths = list(x_txns.keys())
    ledger_updated = {path: False for path in paths}
    updated_txns: dict[path, list[Transaction]] = {}
    for path, txns in x_txns.items():
        new_txns = []
        for txn in txns:
            if utils.is_expired(txn):
                no_expired_txns = False
                txn_ = _update_txn(txn, path)
                if not ledger_updated[path] and txn_ != txn:
                    ledger_updated[path] = True
                txn = txn_
            if txn is not None:
                new_txns.append(txn)
        updated_txns[path] = new_txns

    if no_expired_txns:
        paths_string = "\n".join([str(path) for path in paths])
        print(
            "There are no expired transactions on any of the following"
            f" ledgers:\n{paths_string}"
        )
        return

    updated_paths = [path for path in paths if ledger_updated[path]]
    paths_string = "\n".join([str(path) for path in updated_paths])
    if not updated_paths:
        print(
            "\nYou have not choosen to modify any expired transactions."
            "\nNo ledger has been altered."
        )
        return

    updated_contents: dict[Path, str] = {}
    for path in updated_paths:
        content = utils.create_ledger_content(file_keys[path], updated_txns[path])
        updated_contents[path] = content

    overwrite_ledgers(updated_contents)
    print(f"\nThe following ledgers have been updated:\n{paths_string}")
