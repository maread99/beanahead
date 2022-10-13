"""Plugins for Regular Expected Transactions."""

from beancount.core.data import Entries, Options, Transaction
from beanahead.utils import TAG_RX, RX_META_DFLTS

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
        for k, v in RX_META_DFLTS.items():
            entry.meta.setdefault(k, v)

    return entries, (errors := [])
