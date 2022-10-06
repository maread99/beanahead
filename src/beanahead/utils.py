"""General utility functions."""

import datetime
from pathlib import Path
import re

from beancount import loader
from beancount.core import data
from beancount.core.account_types import is_account_type
from beancount.core.data import Transaction
from beancount.core.interpolate import AUTOMATIC_META
from beancount.ingest.extract import HEADER
from beancount.parser import parser, printer

from .errors import (
    BeancountFileExistsError,
    BeanaheadFileExistsError,
    BeanaheadLedgerFileExistsError,
    BeanaheadFileKeyError,
    BeancountLoaderErrors,
)

# TODO TESTS FOR ALL OF MODULE!!!!

SEPARATOR_LINE = "-" * 77 + "\n"
TODAY = datetime.datetime.now().date()
EXT = ".beancount"

FILE_CONFIG = {
    "x": {
        "title": "Expected Transactions Ledger",
        "plugin": None,
        "tag": "x_txn",
        "comment": "Enter expected transactions after this line...",
        "post_comment": "...enter expected transactions before this line.",
    },
    "rx": {
        "title": "Regular Expected Transactions Ledger",
        "plugin": "rx_txn_plugin",
        "tag": "rx_txn",
        "comment": "Transactions should not be manually added to this file.",
        "post_comment": None,
    },
    "rx_def": {
        "title": "Regular Expected Transaction Definitions",
        "plugin": "rx_txn_plugin",
        "tag": "rx_txn",
        "comment": "Enter definitions after this line...",
        "post_comment": "...enter definitions before this line.",
    },
}

LEDGER_FILE_KEYS = ["x", "rx"]


def validate_file_key(file_key: str):
    """Validate a file_key.

    Raises
    ------
    ValueError
        If `file_key` is not a valid key.
    """
    if file_key not in (valid_keys := FILE_CONFIG.keys()):
        raise ValueError(
            f"'{file_key}' is not a valid file key. `file_key` must be a"
            f" value in {list(valid_keys)}."
        )


def validate_ledger_file_key(file_key: str):
    """Validate a ledger file_key.

    Raises
    ------
    ValueError
        If `file_key` is not a valid ledger file key.
    """
    if file_key not in LEDGER_FILE_KEYS:
        raise ValueError(
            f"'{file_key}' is not a valid ledger file key. `file_key` must be"
            f" a value in {LEDGER_FILE_KEYS}."
        )


def compose_header_footer(file_key: str) -> tuple[str, str]:
    """Compose header and footer for an expected transactions file.

    Parameters
    ----------
    file_key
        key of `FILE_CONFIG` describing nature of file being composed.

    Returns
    -------
    tuple
        [0] header
        [1] footer
    """
    config = FILE_CONFIG[file_key]
    plugin, tag, comment = config["plugin"], config["tag"], config["comment"]

    header = f"""option "title" "{config['title']}"\n"""
    if plugin is not None:
        header += f'plugin "{plugin}"\n'
    header += f"pushtag #{tag}\n"
    if comment is not None:
        header += f";; {comment}\n"

    post_comment = config["post_comment"]
    footer = f";; {post_comment}\n" if post_comment is not None else ""
    footer += f"poptag #{tag}\n"
    return header, footer


def create_beanahead_file(
    file_key: str, dirpath: str | None = None, filename: str | None = None
):
    """Create a new beanahead file.

    Parameters
    ----------
    file_key
        key of `FILE_CONFIG` describing nature of file to be created. From:
            "x" - Expected Transactions Ledger
            "rx" - Regular Expected Transactions Ledger
            "rx_def" - Regular Expected Transaction Definitions file

    dirpath
        Path to directory in which to create new file. Can be absolute or
        relative to the current working directory. Must be an existing
        directory. By default, the current working directory.

    filename
        Name of new beanahead file. By default, same as `file_key`. Should not
        include the .beancount extension.

    Raises
    ------
    NotADirectoryError
        If `dirpath` does not represent a path to an existing directory.

    FileExistsError
        If .beancount file with `filename` already exists at `dirpath`.
    """
    file_key = file_key.lower()
    validate_file_key(file_key)

    dirpath = "." if dirpath is None else dirpath
    dirpath_ = Path(dirpath).absolute()
    if not dirpath_.is_dir():
        raise NotADirectoryError(dirpath_)

    filename = file_key if filename is None else filename
    path = (dirpath_ / filename).with_suffix(EXT)
    if path.is_file():
        raise FileExistsError(path)

    header, footer = compose_header_footer(file_key)
    content = header + "\n\n" + footer

    with path.open("wt", encoding="utf-8") as file:
        file.write(content)


def verify_path(path: Path):
    """Verify path to an existing .beancount file.

    Parameters
    ----------
    path
        Path to be verified.

    Raises
    ------
    BeancountFileExistsError
        If path does not have .beancount suffix.
        If path does not represent an existing file.

    """
    if path.suffix != EXT:
        raise BeancountFileExistsError("path does not have a '.beancount' extension.")
    elif not path.is_file():
        raise BeancountFileExistsError(f"{path} is not a path to an existing file.")


def verify_files_key(path: Path, file_key: str):
    """Verify beancount file is a beanahead file of a specific nature.

    Parameters
    ----------
    path
        path representing beancount file to be verified.

    file_key
        key of `FILE_CONFIG` describing file nature to be verified.

    Raises
    ------
    BeancountFileKeyError
        If the first line of file at `path` does represent the expected
        title for `file_key`.

    See Also
    ---------
    get_verified_file_key : Verify path to a beanahead file and return its
        file key.
    get_verified_ledger_file_key : Verify path to a beanahead ledger file
        and return its file key.
    """
    with path.open("rt", encoding="utf-8") as file:
        first_line = file.readline()
    title = FILE_CONFIG[file_key]["title"]
    if not first_line[:-2].endswith(title):
        raise BeanaheadFileKeyError(
            f"The first line of '{path}' does not contain the expected title '{title}'."
        )


def get_unverified_path(filepath: str) -> Path:
    """Return unverified path to a beancount file.

    Parameters
    ----------
    filepath
        Path to .beancount file, either absolute or relative to the cwd.
        It is not necessary to include the .beancount extension.
    """
    path = Path(filepath).absolute()
    if not path.suffix:
        path = path.with_suffix(EXT)
    return path


def get_verified_path(filepath: str, file_key: str | None = None) -> Path:
    """Return verified path to a beancount file.

    Parameters
    ----------
    filepath
        Path to .beancount file, either absolute or relative to the cwd.
        It is not necessary to include the .beancount extension.

    file_key
        key of `FILE_CONFIG` describing nature of file to be verified.
        If passed then the .beancount file will additionally be verified
        as of the nature described by the file_key (raises
        BeanaheadFileKeyError if not verified).
    """
    path = get_unverified_path(filepath)
    verify_path(path)
    if file_key is not None:
        verify_files_key(path, file_key)
    return path


def get_options(path: Path) -> dict:
    """Get options for a beancount file.

    Parameters
    ----------
    path
        Path to beancount file. Path is NOT verified.

    Returns
    -------
    dict
        Options as mapping of 'option name' : value.
    """
    entries, errors, options = loader.load_file(path)
    return options


def get_verified_file_key(path: Path) -> str:
    """Verify path to a beanahead file and return its file key.

    Parameters
    ----------
    path
        Path to file to be verified.

    Returns
        file_key, as key of `FILE_CONFIG`, corresponding with file at
        `path`.

    Raises
    ------
    BeancountFileExistsError
        If `path` does not represent a beancount file.

    BeanaheadFileExistsError
        If `path` does not represent a beanahead file.

    See Also
    ---------
    get_verified_ledger_file_key : Verify path to a beanahead ledger file
        and return its file key.
    verify_files_key : Verify beancount file is a beanahead file of a
        specific nature.
    """
    verify_path(path)
    opts = get_options(path)
    title = opts["title"]
    all_titles = []
    for file_key, config in FILE_CONFIG.items():
        if title == (config_title := config["title"]):
            return file_key
        all_titles.append(config_title)
    titles_string = "\n".join(all_titles)
    raise BeanaheadFileExistsError(
        f"'{path}' does not represent a beanahead file. Beanahead files have"
        f" one of the following titles:\n{titles_string}"
    )


def get_verified_ledger_file_key(path: Path) -> str:
    """Verify path to a beanahead ledger file and return its file key.

    Parameters
    ----------
    path
        Path to a beanahead Expected Transactions Ledger file.

    Raises
    ------
    BeancountFileExistsError
        If `path` does not represent a beancount file.

    BeanaheadFileExistsError
        If `path` does not represent a beanahead file.

    BeanaheadLedgerFileExistsError
        If `path` represents a beanahead file, but not a beanahead
        Expected Transactions Ledger.

    See Also
    ---------
    get_verified_file_key : Verify path to a beanahead file and return its
        file key.
    verify_files_key : Verify beancount file is a beanahead file of a
        specific nature.
    """
    file_key = get_verified_file_key(path)
    if file_key not in LEDGER_FILE_KEYS:
        raise BeanaheadLedgerFileExistsError(path)
    return file_key


def get_unverified_entries(path: Path) -> data.Entries:
    """Get entries from a ledger file.

    Function is unconcerned with whether errors are raised when entries
    are loaded from the ledger.

    Parameters
    ----------
    path
        Path to ledger file.

    Returns
    -------
    data.Entries
        Entries extracted from unverified ledger file.
    """
    entries, errors, options = loader.load_file(path)
    return entries


def get_verified_entries(path: Path) -> data.Entries:
    """Get verified entries for a ledger file.

    Parameters
    ----------
    path
        Path to ledger file.

    Raises
    ------
    BeancountLoaderErrors
        If beancount raises any error when loading / attempting to
        load the ledger file.

    Returns
    -------
    data.Entries
        Entries extracted from verified ledger file.
    """
    entries, errors, options = loader.load_file(path)
    if errors:
        raise BeancountLoaderErrors(path, errors)
    return entries


def extract_txns(entries: data.Entries) -> list[Transaction]:
    """Return only entries that are transactions.

    Parameters
    ----------
    entries
        Entries to be filtered.
    """
    return [entry for entry in entries if isinstance(entry, Transaction)]


def get_unverified_txns(path: Path) -> list[Transaction]:
    """Get unverified transactions from a ledger file.

    Function is unconcerned with whether errors are raised when entries
    are loaded from the ledger.

    Parameters
    ----------
    path
        Path to ledger file.

    Returns
    -------
    list of Transaction
        Transactions extracted from unverified ledger file.
    """
    entries = get_unverified_entries(path)
    return extract_txns(entries)


def get_verified_txns(path: Path) -> list[Transaction]:
    """Get verified transactions from a ledger file.

    Parameters
    ----------
    path
        Path to ledger file.

    Returns
    -------
    list of Transaction
        Transactions extracted from verified ledger file.
    """
    entries = get_verified_entries(path)
    return extract_txns(entries)


def is_expired(txn: Transaction) -> bool:
    """Query if a transaction has expired.
    
    Returns
    -------
    bool
        True if `txn` is dated prior to today. False otherwise.
    """
    return txn.date < TODAY


def get_expired_txns(txns: list[Transaction]) -> list[Transaction]:
    """Get transactions dated prior to today."""
    return [txn for txn in txns if is_expired(txn)]


def remove_txns(
    txns: list[Transaction], txns_to_remove: list[Transaction]
) -> list[Transaction]:
    """Remove specific transactions from a list of transactions.

    All `txns_to_remove` must be present in `txns`.

    Parameters
    ----------
    txns
        List of transactions from which transactions are to be removed.

    txns_to_remove
        List of transactions to remove from `txns`.

    Returns
    -------
    Copy of `txns` excluding transactions in `txns_to_remove`.

    Raises
    ------
    ValueError
        If any item in txns_to_remove` is not in `txns`.
    """
    rtrn = [txn for txn in txns if txn not in txns_to_remove]
    if len(rtrn) > len(txns) - len(txns_to_remove):
        not_in_txns = [txn for txn in txns_to_remove if txn not in txns]
        assert not_in_txns
        raise ValueError(
            "The following items are in `txns_to_remove` although not"
            f" in `txns`:\n{not_in_txns}."
        )
    return rtrn


def reverse_automatic_balancing(txn: Transaction) -> Transaction:
    """Return copy of a transaction with any interpolation reversed.

    Parameters
    ----------
    txn
        Transaction from which to reverse any automatic balancing.
    """
    new_postings = []
    for posting in txn.postings:
        if AUTOMATIC_META in posting.meta:
            meta = {k: v for k, v in posting.meta.items() if k != AUTOMATIC_META}
            posting = posting._replace(units=None, meta=meta)
        new_postings.append(posting)
    return txn._replace(postings=new_postings)


def is_assets_account(string: str) -> bool:
    """Query if a string represents an assets account."""
    return is_account_type("Assets", string)


def get_assets_accounts(txn: Transaction) -> list[str]:
    """Get all assets accounts assigned to a transaction's postings.

    Parameters
    ----------
    txn
        Transaction to query.

    Raises
    ------
    ValueError
        If `txn` has no posting to an Assets account.
    """
    accounts = [
        post.account for post in txn.postings if is_assets_account(post.account)
    ]
    if not accounts:
        raise ValueError(f"Transaction has no posting to an Assets account:\n{txn}")
    return accounts


def get_content(path: Path) -> str:
    """Get all content from a file.

    Parameters
    ----------
    path
        Path to file from which to get all content.
    """
    with path.open("r", encoding="utf-8") as file:
        content = file.read()
    return content


def compose_entries_content(entries: data.Directive | data.Entries) -> str:
    """Return printable string representing one or more entries."""
    if isinstance(entries, data.Directive):
        entries = [entries]
    content = ""
    for entry in entries:
        if isinstance(entry, Transaction):
            entry = reverse_automatic_balancing(entry)
        content += printer.format_entry(entry) + "\n"
    return content[:-1]


def compose_new_content(file_key: str, txns_content: str) -> str:
    """Compose full content of an expected transactions .beancount file.

    Parameters
    ----------
    file_key
        key of `FILE_CONFIG` describing nature of file being composed.

    txns_content
        Content of transactions to be included to file.

    Returns
    -------
    str
        Content to overwrite an expected transactions .beancount file of
        nature described by `file_key`.

    Raises
    ------
    ValueError
        If created content parses with errors.
    """
    header, footer = compose_header_footer(file_key)
    content = header + "\n\n" + txns_content + "\n\n" + footer
    _, errors, _ = parser.parse_string(content)
    if errors:
        raise ValueError(f"New content parses with following errors: {errors}")
    return content


def write(path: Path, content: str):
    """Write content to path."""
    with path.open("wt", encoding="utf-8") as file:
        file.write(content)


def overwrite_file(path: Path, content: str):
    """Overwrite file with content for an expected transactions file.

    Parameters
    ----------
    path
        Path to file to be overwritten.

    content
        Content to write to file at `path`.

    Raises
    ------
    ValueError
        If `content` would subsequently load with errors.
    """
    _, errors, _ = parser.parse_string(content)
    if errors:
        raise ValueError(
            f"{path} has not been overwritten as content would parse with following"
            f" errors: {errors}"
        )
    write(path, content)


def create_ledger_content(file_key: str, txns: list[Transaction]) -> str:
    """Create content for a beanahead ledger file.

    Parameters
    ----------
    file_key
        key of `FILE_CONFIG` describing nature of ledger for which
        content required.

    txns
        List of all expected transactions to be included in the content.
    """
    validate_ledger_file_key(file_key)
    txns_content = compose_entries_content(txns)
    return compose_new_content(file_key, txns_content)


def remove_txns_from_ledger(path: Path, txns: list[Transaction]):
    """Remove txns from an Expected Transactions Ledger.

    Expected Transactions Ledger at `path` will be overwritten with
    existing transactions excluding `txns`.

    NOTE Entries will be sorted and any comments on the the existing file
    will be lost.

    Parameters
    ----------
    path
        Path to Expected Transactions Ledger from which `txns` are to be
        removed.

    txns
        Transactions to remove from the ledger.
    """
    file_key = get_verified_ledger_file_key(path)
    existing_txns = get_unverified_txns(path)
    retained_txns = remove_txns(existing_txns, txns)
    new_content = create_ledger_content(file_key, retained_txns)
    overwrite_file(path, new_content)


# TODO TEST VIA doctest
def compile_words_regex(
    words: str | list[str], reject: str | list[str] | None = None, flags=re.I
) -> re.Pattern:
    """Return regex to match one or more words in any order.

    Parameters
    ----------
    words
        Words to match.

    reject
        List of words to not match. If any word in the `reject` list is
        present then the regex will not match.

    flags : default: re.I
        re module flags. Combine more than one with | operator. Pass None
        to not add any flag.

    Returns
    -------
    re.Pattern
        Compiled regex.
    """
    if isinstance(words, str):
        words = [words]
    regex = "^" + "".join([rf"(?=.*\b{word}\b)" for word in words])
    if reject is not None:
        if isinstance(reject, str):
            reject = [reject]
        regex += "".join([rf"(!=.*\b{word}\b)" for word in reject])
    regex += ".*$"
    return re.compile(regex, flags)


def response_is_valid_number(response: str, max_value: int) -> bool:
    """Query if a response represents an integer less than a max_value."""
    try:
        response = int(response)
    except ValueError:
        return False
    return 0 <= response <= max_value


def inject_txns(injection: str, ledger: str):
    """Inject new transactions to a ledger.

    New transactions are injected by way of appending the contents of
    the `injection` file to the end of the `ledger` file.

    Parameters
    ----------
    All parameters can be passed as either absolute paths or paths relative
    to the cwd. It is not necessary to include the. beancount extension.
    For example, "rx" would refer to the file 'rx.beancount' in the cwd.

    injection : str
        Path to .beancount file containing the new transactions to be
        injected to `ledger`.

    ledger: str
        Path to .beancount ledger file to which the new transactions are
        to be injected.
    """
    injection_path = get_verified_path(injection)
    content = get_content(injection_path)
    if content.startswith(HEADER):
        content = content[len(HEADER):]
    content = "\n" + content
    ledger_path = get_verified_path(ledger)

    with ledger_path.open("at", encoding="utf-8") as file:
        file.write(content)
