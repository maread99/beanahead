"""Configuration file for options."""

from __future__ import annotations

import configparser
import enum
import pathlib
import sys
import warnings
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Sequence

ENCODING = "utf-8"

CONFIG_DIR = pathlib.Path("~/.config/beanahead").expanduser()
CONFIG_FILE = CONFIG_DIR / "config.ini"


SETTINGS_DFLTS = {
    "name-assets": "Assets",
    "name-liabilities": "Liabilities",
    "name-equity": "Equity",
    "name-income": "Income",
    "name-expenses": "Expenses",
    "print-stream": "stdout",
    "extension": "beancount",
}
_comments = {
    "print-stream": "from ('stdout', 'stderr')",
    "extension": "Default extension for beancount files",
}
_lines = [
    f"{k} = {v}" + (("  # " + _comments[k]) if k in _comments else "")
    for k, v in SETTINGS_DFLTS.items()
]
_lines.insert(sum(k.startswith("name") for k in SETTINGS_DFLTS), "")
DFLT_CONFIG = "[DEFAULT]\n# Account root names\n" + "\n".join(_lines) + "\n"

BC_DEFAULT_ACCOUNT_ROOT_NAMES = {
    k.replace("-", "_"): v for k, v in SETTINGS_DFLTS.items() if k.startswith("name")
}


def print_config_file_path():
    """Print address of configuration file to stdout."""
    print(f"The beanahead configuration file can be found at:\n\t{CONFIG_FILE}")  # noqa: T201


def print_default_config():
    """Print contents of default configuration file to stdout."""
    print(DFLT_CONFIG)  # noqa: T201


def _write_config():
    """Write default configuration file."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(DFLT_CONFIG, encoding=ENCODING)


def reset_config():
    """Reset the configuration file to the default values."""
    _write_config()


class ConfigWarning(UserWarning):
    """User warning to advise of invalid values in the configuration file."""

    _msg = "Configuration Warning"  # subclass should override

    def __str__(self) -> str:
        return self._msg


class ConfigInvalidOptionsWarning(ConfigWarning):
    """The configuration file includes invalid options."""

    def __init__(self, invalid_keys: set[str]):
        self._msg = (
            "The configuration file includes the following invalid options:"
            f" '{invalid_keys}'.\nThese options will be ignored."
        )


class ConfigInvalidValueWarning(ConfigWarning):
    """The configuration file includes an option with an invalid value."""

    def __init__(
        self,
        key: str,
        value: str,
        dflt: str,
        valid_values: Sequence[Any] | None = None,
    ):
        self._msg = (
            f"'{value}' is not a valid value for the configuration option {key}."
            f" The default value '{dflt}' will be used."
        )
        if valid_values is not None:
            self._msg += f"\nValid values for '{key}' are: {valid_values}."


warnings.simplefilter("always", ConfigInvalidValueWarning)


class PrintStream(enum.Enum):
    """Enumerator for print stream values."""

    STDOUT = "stdout"
    STDERR = "stderr"


@dataclass
class Settings:
    """Configuration settings."""

    name_assets: str
    name_liabilities: str
    name_equity: str
    name_income: str
    name_expenses: str
    print_stream: PrintStream
    extension: str

    @property
    def print_to(self):
        """TextIO to print to."""
        return sys.stdout if self.print_stream is PrintStream.STDOUT else sys.stderr


def parse_config(config: configparser.SectionProxy) -> Settings:
    """Verify configuration settings."""
    invalid_keys = set(config) - set(SETTINGS_DFLTS)
    if invalid_keys:
        warnings.warn(ConfigInvalidOptionsWarning(invalid_keys))  # noqa: B028
    settings = {}
    for k, v in config.items():
        if k in invalid_keys:
            continue
        v = v.strip()  # noqa: PLW2901
        if " " in v:
            warnings.warn(ConfigInvalidValueWarning(k, v, SETTINGS_DFLTS[k], None))  # noqa: B028
            v = SETTINGS_DFLTS[k]  # noqa: PLW2901
        if k == "print-stream":
            valid_values = [m.value for m in PrintStream]
            if v not in valid_values:
                warnings.warn(  # noqa: B028
                    ConfigInvalidValueWarning(k, v, SETTINGS_DFLTS[k], valid_values)
                )
                v = SETTINGS_DFLTS[k]  # noqa: PLW2901
            v = PrintStream(v)  # noqa: PLW2901
        if k == "extension" and not v.startswith("."):
            v = "." + v  # noqa: PLW2901
        settings[k.replace("-", "_")] = v
    return Settings(**settings)


def load_config() -> configparser.SectionProxy:
    """Load configuration file.

    If config file does not exist, create one with default values.
    """
    if not CONFIG_FILE.exists():
        _write_config()

    config = configparser.ConfigParser(
        defaults=SETTINGS_DFLTS,
        inline_comment_prefixes=("#",),
        empty_lines_in_values=False,
    )
    config.read(CONFIG_FILE)
    return config["DEFAULT"]


def get_settings_from_config() -> Settings:
    """Get settings from configuration file."""
    return parse_config(load_config())


SETTINGS: Settings = get_settings_from_config()


def reset_settings():
    """Set settings according to configuration file."""
    global SETTINGS  # noqa: PLW0603
    SETTINGS = get_settings_from_config()


def get_account_root_names() -> dict[str, str]:
    """Get account root names."""
    return {
        k.replace("-", "_"): getattr(SETTINGS, k.replace("-", "_"))
        for k in SETTINGS_DFLTS
        if k.startswith("name")
    }


def set_account_root_names(names: dict):
    """Set account root names.

    Use this method to override the account root names as defined on the
    configuration file.

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
    """
    keys = {k.replace("-", "_") for k in SETTINGS_DFLTS}
    diff = set(names) - keys
    if diff:
        raise ValueError(
            f"'names' parameter can only contain keys: {keys},"
            f" although received 'names' included keys: {diff}."
        )
    for k, v in names.items():
        setattr(SETTINGS, k, v)
