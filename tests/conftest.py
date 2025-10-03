"""Common pytest fixtures and hooks."""

import configparser
import copy
import datetime
import io
import os
import shutil
import sys
import textwrap
from collections import abc
from pathlib import Path

import beancount
import pytest
from beancount.core import data

from beanahead import config, utils

ENCODING = "utf-8"
TEST_ROOT = Path(__file__).parent
TEMP_DIR = TEST_ROOT / r"./_temp"
TEMP_SUBDIR = TEMP_DIR / r"./_tempsub"
for _temp_dir in (TEMP_DIR, TEMP_SUBDIR):
    if not _temp_dir.is_dir():
        _temp_dir.mkdir()


def set_cl_args(cl: str):
    """Set system command line arguments.

    Parameters
    ----------
    cl
        String representing command passed to command line, for example
        'beanahead exp x rx'
    """
    args = cl.split(" ")
    args.insert(0, "beanahead")
    sys.argv = args


def get_fileobj(filepath: Path, mode="r") -> io.TextIOWrapper:
    return filepath.open(mode, encoding=ENCODING)


def get_entries_from_string(string: str) -> data.Entries:
    """Get entries as parsed from a string."""
    string = textwrap.dedent(string)
    entries, _, _ = beancount.loader.load_string(string)
    return entries


def get_expected_output(string: str):
    """Convert raw triple quoted string to string representing expected output."""
    return textwrap.dedent(string)[1:]


def pytest_sessionstart(session):  # noqa: ARG001
    """Hook executed before session starts.

    Cleans temporary test folder and patches settings to default.
    """
    _clean_test_dir()


@pytest.fixture
def path_config_dflt(config_dir: Path) -> abc.Iterator[Path]:
    """Path to default configuration file."""
    path = config_dir / "dflt.ini"
    assert path.exists()
    yield path


@pytest.fixture
def path_config_alt(config_dir: Path) -> abc.Iterator[Path]:
    """Path to alternative configuration file."""
    path = config_dir / "alt.ini"
    assert path.exists()
    yield path


@pytest.fixture
def path_config_alt_ext(config_dir: Path) -> abc.Iterator[Path]:
    """Path to configuration file with alternative extension."""
    path = config_dir / "alt_ext.ini"
    assert path.exists()
    yield path


def get_config(filepath: Path) -> configparser.SectionProxy:
    """Get config file."""
    config = configparser.ConfigParser(
        inline_comment_prefixes=("#",), empty_lines_in_values=False
    )
    config.read(filepath)
    return config["DEFAULT"]


@pytest.fixture
def config_dflt(path_config_dflt: Path) -> abc.Iterator[configparser.SectionProxy]:
    """Config parser section for dlft configuration."""
    yield get_config(path_config_dflt)


@pytest.fixture
def config_alt(path_config_alt: Path) -> abc.Iterator[configparser.SectionProxy]:
    """Config parser section for alternative configuration."""
    yield get_config(path_config_alt)


@pytest.fixture
def config_path_mp_dflt(monkeypatch, path_config_dflt):
    """Mock CONFIG_FILE to alternative configuration file."""
    monkeypatch.setattr("beanahead.config.CONFIG_FILE", path_config_dflt)


@pytest.fixture
def config_path_mp_alt(monkeypatch, path_config_alt):
    """Mock CONFIG_FILE to alternative configuration file."""
    monkeypatch.setattr("beanahead.config.CONFIG_FILE", path_config_alt)


@pytest.fixture
def config_path_mp_alt_ext(monkeypatch, path_config_alt_ext):
    """Mock CONFIG_FILE to configuration file with alternative extension."""
    monkeypatch.setattr("beanahead.config.CONFIG_FILE", path_config_alt_ext)


@pytest.fixture(autouse=True)
def set_dflt_settings(request, monkeypatch, path_config_dflt):
    """Use default settings by default."""
    if "nosetdfltsettings" not in request.keywords:
        monkeypatch.setattr("beanahead.config.CONFIG_FILE", path_config_dflt)
        config.reset_settings()


@pytest.fixture
def reset_settings():
    """Reset config settings."""
    config.reset_settings()


@pytest.fixture
def settings_dflt() -> abc.Iterator[config.Settings]:
    """Expected default settings.

    Settings match those in the default config file.
    """
    yield config.Settings(
        name_assets="Assets",
        name_equity="Equity",
        name_expenses="Expenses",
        name_income="Income",
        name_liabilities="Liabilities",
        print_stream=config.PrintStream.STDOUT,
        extension=".beancount",
    )


@pytest.fixture
def settings_alt() -> abc.Iterator[config.Settings]:
    """Expected alternative settings.

    Settings match those in the alt config file.
    """
    yield config.Settings(
        name_assets="Bienes",
        name_liabilities="Obligaciones",
        name_equity="Participaciones",
        name_income="Ingresos",
        name_expenses="Gastos",
        print_stream=config.PrintStream.STDERR,
        extension=".bean",
    )


@pytest.fixture
def settings_alt_prnt_mp(monkeypatch, settings_dflt):
    settings = copy.copy(settings_dflt)
    settings.print_stream = config.PrintStream.STDERR
    monkeypatch.setattr("beanahead.config.SETTINGS", settings)


@pytest.fixture
def encoding() -> abc.Iterator[str]:
    yield ENCODING


@pytest.fixture
def temp_dir() -> abc.Iterator[Path]:
    yield TEMP_DIR


@pytest.fixture
def cwd_as_temp_dir(temp_dir) -> abc.Iterator[Path]:
    """Set cwd to `tests._temp` over fixture's duration.

    Yields temporary cwd.
    """
    prev_cwd = Path.cwd()
    os.chdir(temp_dir)
    yield Path.cwd()
    os.chdir(prev_cwd)


def _clean_test_dir():
    """Remove all files and directories from the test directory."""
    for dirpath, _dirnames, filenames in os.walk(TEMP_DIR):
        path_dir = Path(dirpath)
        for filename in filenames:
            path = path_dir / filename
            path.unlink()
        if not dirpath.endswith("_temp") and not dirpath.endswith("_tempsub"):
            path_dir.rmdir()


@pytest.fixture(autouse=True)
def clean_test_dir() -> abc.Iterator[Path]:
    _clean_test_dir()
    yield


@pytest.fixture
def mock_input(monkeypatch) -> abc.Iterator:
    """Mock built-in input command to return pre-defined responses."""

    class MockInput:
        def __init__(self, responses: abc.Generator[str]):
            self.responses = responses
            monkeypatch.setattr("beanahead.utils.get_input", self.input)

        def input(self, string: str) -> str:
            utils.print_it(string)
            return next(self.responses)

    yield MockInput


@pytest.fixture
def res_dir() -> abc.Iterator[Path]:
    yield TEST_ROOT / "resources"


@pytest.fixture
def recon_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "recon"


@pytest.fixture
def config_dir(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "config"


# Common fixtures from files in recon folder


@pytest.fixture
def filepath_recon_x(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "x.beancount"


@pytest.fixture
def filepath_recon_rx(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "rx.beancount"


@pytest.fixture
def filepath_recon_extraction(recon_dir) -> abc.Iterator[Path]:
    yield recon_dir / "extraction.beancount"


@pytest.fixture
def filepaths_recon_copy(
    filepath_recon_extraction, filepath_recon_rx, filepath_recon_x, temp_dir
) -> abc.Iterator[dict[str, Path]]:
    """Filepaths to copies of files before reconciling new transactions.

    Copies of each file saved to temporary folder.

    Yields mapping to temporary paths with keys as:
        "extraction" - file representing extracted transactions
        "rx" - expected regular transactions ledger
        "x" - expected transactions ledger
    """
    d = {}
    for k, filepath in zip(
        ("extraction", "rx", "x"),
        (filepath_recon_extraction, filepath_recon_rx, filepath_recon_x),
        strict=True,
    ):
        string = shutil.copy(filepath, temp_dir)
        d[k] = Path(string)
    yield d
    for path in d.values():
        path.unlink()


# Common fixtures from files in resources folder


@pytest.fixture
def filepath_ledger_txns(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_ledger_txns.beancount"


@pytest.fixture
def filepath_rx(res_dir) -> abc.Iterator[Path]:
    yield res_dir / "example_rx.beancount"


@pytest.fixture
def txns_ledger(filepath_ledger_txns) -> abc.Iterator[list[data.Transaction]]:
    txns, _errors, _options = beancount.loader.load_file(filepath_ledger_txns)
    yield txns


@pytest.fixture
def txn(txns_ledger) -> abc.Iterator[data.Transaction]:
    yield txns_ledger[0]


@pytest.fixture
def txns_rx(filepath_rx) -> abc.Iterator[list[data.Transaction]]:
    txns, _errors, _options = beancount.loader.load_file(filepath_rx)
    yield txns


@pytest.fixture
def rx_txn_edison(txns_rx) -> abc.Iterator[data.Transaction]:
    txn = txns_rx[1]
    assert txn.payee == "EDISON"
    assert txn.date == datetime.date(2022, 10, 5)
    yield txn


@pytest.fixture
def rx_txn_chase(txns_rx) -> abc.Iterator[data.Transaction]:
    txn = txns_rx[-1]
    assert txn.payee == "Chase"
    assert txn.date == datetime.date(2022, 10, 31)
    yield txn


@pytest.fixture
def account_root_names_dflt() -> abc.Iterator[dict[str, str]]:
    """Expected default account_root_names."""
    yield {
        "name_assets": "Assets",
        "name_liabilities": "Liabilities",
        "name_equity": "Equity",
        "name_income": "Income",
        "name_expenses": "Expenses",
    }
