"""Script for dispatching from command line.

Notes
-----
This module does not have a dedicated tests module, rather for each
subcommand a test is included to the test module for the module on which
the corresponding underlying function is located.
"""

import argparse
import datetime

import beanahead
from beanahead import utils, rx_txns, reconcile, expired


def make_file(args: argparse.Namespace):
    """Pass through command line args to make a new beanahead file."""
    utils.create_beanahead_file(args.key, args.dirpath, args.filename)


def add_rx_txns(args: argparse.Namespace):
    """Pass through command line args to add rx txns."""
    admin = rx_txns.Admin(args.defs, args.ledger, args.main)
    admin.add_txns(args.end)


def recon(args: argparse.Namespace):
    """Pass through command line args to reconcile new transactions."""
    reconcile.reconcile_new_txns(
        new_entries=args.new,
        x_txns_ledgers=args.ledgers,
        remove=not args.keep,
        output=args.output,
        ascending=not args.reverse,
    )


def exp(args: argparse.Namespace):
    """Pass through command line args to administer expired transactions."""
    expired.admin_expired_txns(args.ledgers)


def inj(args: argparse.Namespace):
    """Pass through command line args to inject new transactions."""
    utils.inject_txns(args.injection, args.ledger)


def main():
    """Entry point for calls from the command line."""
    parser = argparse.ArgumentParser(
        description=(
            "Create expected transactions ledgers, generate regular expected"
            "\ntransactions and reconcile expected transactions against"
            "\nnew transactions."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument(
        "--version", "-V", action="version", version=beanahead.__version__
    )

    subparsers = parser.add_subparsers(
        title="subcommands",
        dest="subcmd",
        required=True,
    )

    # Subparser for make_file
    parser_make = subparsers.add_parser(
        "make",
        description="Make a new beanahead ledger or definitions file.",
        help="make a new beanahead file.",
        epilog=(
            "Documentation of underlying function:"
            f"\n\n{utils.create_beanahead_file.__doc__}"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser_make.add_argument(
        "key",
        help=(
            "Nature of beanahead file to create."
            "\n\t'x' Expected Transactions Ledger"
            "\n\t'rx' Regular Expected Transactions Ledger"
            "\n\t'rx_def' Regular Expected Transactions Definitions"
        ),
        choices=["x", "rx", "rx_def"],
        metavar="key",
    )
    parser_make.add_argument(
        *["-d", "--dirpath"],
        help=(
            "Path to directory in which to create new file. Can be"
            "\nabsolute or relative to the current working directory."
            "\nMust be an existing directory. By default, the current"
            "\nworking directory."
        ),
        metavar="",
    )
    parser_make.add_argument(
        *["-f", "--filename"],
        help=(
            "Name of new beanahead file. By default, as `key`.\nShould not"
            " include the .beancount extension."
        ),
        metavar="",
    )
    parser_make.set_defaults(func=make_file)

    # Subparser for add_rx_txns
    parser_addrx = subparsers.add_parser(
        "addrx",
        description=(
            "Add Regular Expected Transactions to a Regular Expected"
            " Transactions Ledger."
        ),
        help="add Regular Expected Transactions.",
        epilog=(
            "Documentation of underlying class:"
            f"\n\n{rx_txns.Admin.__doc__}"
            "\nDocumentation of underlying function:"
            f"\n\n{rx_txns.Admin.add_txns.__doc__}"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser_addrx.add_argument(
        "defs",
        help="path to Regular Expected Transactions Definition file.",
    )
    parser_addrx.add_argument(
        "ledger",
        metavar="rx-ledger",
        help="path to Regular Expected Transactions Ledger file.",
    )
    parser_addrx.add_argument(
        "main",
        metavar="main-ledger",
        help="path to main Ledger file.",
    )

    parser_addrx.add_argument(
        *["-e", "--end"],
        help=(
            "date to which to create new transactions, iso format,"
            f"e.g. '2020-09-30'. Default {rx_txns.END_DFLT}."
        ),
        default=rx_txns.END_DFLT,
        type=datetime.date.fromisoformat,
        metavar="",
    )
    parser_addrx.set_defaults(func=add_rx_txns)

    # Subparser for recon
    parser_recon = subparsers.add_parser(
        "recon",
        description=("Reconcile new transactions with expected transactions."),
        help="reconcile new transactions.",
        epilog=(
            "Documentation of underlying function:"
            f"\n\n{reconcile.reconcile_new_txns.__doc__}"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser_recon.add_argument(
        "new",
        help=(
            "path to new transactions beancount file. Can be"
            "\nabsolute or relative to the current working directory."
        ),
    )
    parser_recon.add_argument(
        "ledgers",
        nargs="+",
        help=(
            "paths to one or more Regular Expected Transactions"
            "\nLedgers against which to reconcile incoming"
            "\ntransactions."
        ),
    )
    parser_recon.add_argument(
        *["-o", "--output"],
        help=(
            "path to which to write updated new entries. Can be"
            "\nabsolute or relative to the current working directory."
            "\nBy default will overwrite 'incoming'."
        ),
    )
    parser_recon.add_argument(
        *["-k", "--keep", "--no-remove"],
        action="store_true",
        help=(
            "flag to not remove reconciled transactions from ledgers.\n"
            "(By default reconciled transactions will be removed.)"
        ),
    )
    parser_recon.add_argument(
        *["-r", "--reverse"],
        action="store_true",
        help=(
            "flag to write updated entries in descending order. By"
            "\ndefault will be written in ascending order."
        ),
    )
    parser_recon.set_defaults(func=recon)

    # Subparser for expired
    parser_exp = subparsers.add_parser(
        "exp",
        description=("Administer expired expected transactions."),
        help="administer expired expected transactions.",
        epilog=(
            "Documentation of underlying function:"
            f"\n\n{expired.admin_expired_txns.__doc__}"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser_exp.add_argument(
        "ledgers",
        nargs="+",
        help=(
            "paths to one or more Regular Expected Transactions Ledgers"
            "\nagainst which to administer expired transactions."
        ),
    )
    parser_exp.set_defaults(func=exp)

    # Subparser for inject
    parser_inject = subparsers.add_parser(
        "inject",
        description=("Append new transactions to a ledger."),
        help="inject new transactions.",
        epilog=(
            "Documentation of underlying function:" f"\n\n{utils.inject_txns.__doc__}"
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser_inject.add_argument(
        "injection",
        help=(
            "path to beancount file containing the new entries to be"
            "\ninjected. Can be absolute or relative to the current"
            "\nworking directory."
        ),
    )

    parser_inject.add_argument(
        "ledger",
        help=(
            "path to beancount ledger to which new entires are to"
            "\nbe appended. Can be absolute or relative to the current"
            "\nworking directory."
        ),
    )
    parser_inject.set_defaults(func=inj)

    # Call pass-through function corresponding with subcommand
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
