"""Configuration file for options."""

import sys

_print_stdout = True


def get_print_file():
    """Get stream to print to."""
    return sys.stdout if _print_stdout else sys.stderr


def set_print_stdout():
    """Set output stream for print to stdout."""
    global _print_stdout
    _print_stdout = True


def set_print_stderr():
    """Set output stream for print to stderr."""
    global _print_stdout
    _print_stdout = False


DEFAULT_ACCOUNT_ROOT_NAMES = {
    "name_assets": "Assets",
    "name_liabilities": "Liabilities",
    "name_equity": "Equity",
    "name_income": "Income",
    "name_expenses": "Expenses",
}

_account_root_names = DEFAULT_ACCOUNT_ROOT_NAMES.copy()


def get_account_root_names() -> dict[str, str]:
    """Get account root names."""
    return _account_root_names.copy()


def set_account_root_names(names: dict) -> dict[str, str]:
    """Set account root names.

    Use this method to set the account root names.

    Default account root names that otherwise prevail are:
    {
        'name_assets': 'Assets',
        'name_liabilities': 'Liabilities',
        'name_equity': 'Equity',
        'name_income': 'Income',
        'name_expenses': 'Expenses',
    }

    Parameters
    ----------
    names
        Dictionary with:
            keys: str
                Any of the account root name options {'name_assets',
                'name_expenses', 'name_income', 'name_liabilities',
                'name_equity'}

            values: str
                Corresponding account root name.

    Returns
    -------
    account_root_names: dict[str, str]
        Newly set account root names.
    """
    global _account_root_names
    diff = set(names) - set(_account_root_names)
    if diff:
        raise ValueError(
            f"'names' parameter can only contain keys: {set(_account_root_names)},"
            f" although received 'names' included keys: {diff}"
        )
    _account_root_names |= names
    set_names = get_account_root_names()
    assert _account_root_names == set_names
    return set_names


def reset_account_root_names() -> dict[str, str]:
    """Set account root names to default values.

    Default account root names are:
    {
        'name_assets': 'Assets',
        'name_liabilities': 'Liabilities',
        'name_equity': 'Equity',
        'name_income': 'Income',
        'name_expenses': 'Expenses',
    }

    Returns
    -------
    account_root_names: dict[str, str]
        Newly set account root names.
    """
    global _account_root_names
    _account_root_names |= DEFAULT_ACCOUNT_ROOT_NAMES
    set_names = get_account_root_names()
    assert _account_root_names == set_names
    return set_names
