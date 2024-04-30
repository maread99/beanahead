from beancount.core.data import Transaction, Entries
from beancount.ingest import extract

from . import utils
from . import reconcile
from .errors import BeanaheadWriteError


class ReconcileExpected:
    """
    Hook class for smart_importer to reconcile expected entries on the fly.

    You also need to use the adapted duplicate hook to avoid false positives
    using the new style import invocation:

        ...
        hools = [ReconcileExpected.adapted_find_duplicate_entries]
        beancount.ingest.scripts_utils.ingest(CONFIG, hooks=hooks)
    """

    def __init__(self, x_txns_file):
        path = utils.get_verified_path(x_txns_file)
        utils.set_root_accounts_context(x_txns_file)
        _ = utils.get_verified_ledger_file_key(path)  # just verify that a ledger
        self.expected_txns_path = path
        self.expected_txns: list[Transaction] = utils.get_unverified_txns(path)

    def __call__(self, importer, file, imported_entries, existing_entries) -> Entries:
        """Apply the hook and modify the imported entries.

        Args:
            importer: The importer that this hooks is being applied to.
            file: The file that is being imported.
            imported_entries: The current list of imported entries.
            existing_entries: The existing entries, as passed to the extract
                function.

        Returns:
            The updated imported entries.
        """
        new_txns, new_other = reconcile.separate_out_txns(imported_entries)
        reconciled_x_txns = reconcile.reconcile_x_txns(self.expected_txns, new_txns)

        updated_new_txns = reconcile.update_new_txns(new_txns, reconciled_x_txns)
        updated_entries = updated_new_txns + new_other

        # Update expected transation file
        x_txns_to_remove = []
        for x_txn, _ in reconciled_x_txns:
            if x_txn in self.expected_txns:
                x_txns_to_remove.append(x_txn)

        prev_contents = utils.get_content(self.expected_txns_path)
        try:
            utils.remove_txns_from_ledger(self.expected_txns_path, x_txns_to_remove)
        except Exception as err:
            utils.write(self.expected_txns_path, prev_contents)
            raise BeanaheadWriteError(
                self.expected_txns_path, [self.expected_txns_path]
            ) from err

        return updated_entries

    @staticmethod
    def adapted_find_duplicate_entries(new_entries_list, existing_entries):
        keep = []
        # filter out expected transactions from duplicate detection
        for entry in existing_entries:
            if isinstance(entry, Transaction) and utils.TAGS_X & entry.tags:
                continue
            keep.append(entry)
        return extract.find_duplicate_entries(new_entries_list, keep)
