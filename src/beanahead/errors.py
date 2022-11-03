"""Beanahead error classes."""

from __future__ import annotations

from pathlib import Path


class BeancountFileExistsError(FileExistsError):
    """A declared beancount file does not exist."""


class BeanaheadFileExistsError(FileExistsError):
    """A declared beanahead file does not exist."""


class BeanaheadFileKeyError(Exception):
    """A file does not reflect the expected beanahead file key."""


class RegularTransactionsDefinitionError(Exception):
    """Error in a regular transactions definition file"""


class BeanaheadLedgerFileExistsError(FileExistsError):
    """A file is a beanahead file, but not a ledger."""

    def __init__(self, path: Path):
        self._msg = (
            f"'{path}' does not represent a beanahead Expected Transactions"
            " Ledger file. NB The path does represent another beanahead file."
            " Might you have passed a Regular Expected Transactions Definitions"
            " file by mistake?"
        )

    def __str__(self) -> str:
        return self._msg


class BeancountLoaderErrors(Exception):
    """Errors returned when loading ledger file."""

    def __init__(self, path: Path, errors: list[Exception]):
        self._msg = (
            "The following errors were raised when attempting to load"
            f" ledger from {path}:\n{errors}."
        )

    def __str__(self) -> str:
        return self._msg


class BeanaheadWriteError(Exception):
    """An error was raised when attempting to write/overwrite a file.

    Parameters
    ----------
    path
        Path to file that attempted to write/overwrite.

    reverted
        List of paths of files that were overwritten although were
        restored to most recent saved content in light of error in
        attempting to write/overwrite `path`.

    overwrite
        True if error raised when attempting to overwrite an existing file.
        False if error raised when attempting to write a new file.
    """

    def __init__(
        self,
        path: Path,
        reverted: list[Path] | None = None,
        overwrite: bool = True,
    ):
        insert = "overwrite" if overwrite else "write to"
        self.msg = f"An error occurred when attempting to {insert} '{path}'."
        if reverted is not None and reverted:
            reverted_files = "\n".join([str(path) for path in reverted])
            self.msg += (
                " The following files have been reverted to their most recent"
                f" saved content:\n{reverted_files}"
            )

    def __str__(self):
        return self.msg
