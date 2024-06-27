"""Configuration file for options."""

import sys

_print_stdout = True


def set_print_stdout():
    """Set output stream for print to stdout."""
    global _print_stdout
    _print_stdout = True


def set_print_stderr():
    """Set output stream for print to stderr."""
    global _print_stdout
    _print_stdout = False


def get_print_file():
    """Get stream to print to."""
    return sys.stdout if _print_stdout else sys.stderr
