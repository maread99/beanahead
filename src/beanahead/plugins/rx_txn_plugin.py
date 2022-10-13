"""Plugins for Regular Expected Transactions."""

from beancount.core.data import Entries, Options, Transaction
from beanahead.utils import TAG_RX

__plugins__ = ["convert_meta"]


def convert_meta(entries: Entries, _: Options) -> tuple[Entries, list[tuple]]:
    """Set default values for Regular Expected Transaction meta fields.

    Parameters
    ----------
    entries
        Entries being loaded.
    """
    for entry in entries:
        if (not isinstance(entry, Transaction)) or TAG_RX not in entry.tags:
            continue
        entry.meta.setdefault("name", entry.payee)
        entry.meta.setdefault("final", None)
        entry.meta.setdefault("roll", True)

    return entries, (errors := [])
