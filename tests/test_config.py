"""Tests for `config` module."""

import copy
import pathlib
import sys
import textwrap
from collections import abc

import pytest

from beanahead import config as m
from beanahead.scripts import cli

from .conftest import set_cl_args


@pytest.fixture
def dflt_config() -> abc.Iterator[str]:
    """Default config file."""
    yield textwrap.dedent(
        """\
        [DEFAULT]
        # Account root names
        name-assets = Assets
        name-liabilities = Liabilities
        name-equity = Equity
        name-income = Income
        name-expenses = Expenses

        print-stream = stdout  # from ('stdout', 'stderr')
        extension = beancount  # Default extension for beancount files
        """
    )


@pytest.mark.nosetdfltsettings
@pytest.mark.usefixtures("reset_settings")
def test_constants(account_root_names_dflt, encoding, dflt_config):
    """Verify value of constants."""
    assert m.ENCODING == "utf-8" == encoding
    assert pathlib.Path("~/.config/beanahead").expanduser() == m.CONFIG_DIR
    assert (
        pathlib.Path("~/.config/beanahead").expanduser() / "config.ini" == m.CONFIG_FILE
    )
    assert m.SETTINGS_DFLTS == {
        "name-assets": "Assets",
        "name-liabilities": "Liabilities",
        "name-equity": "Equity",
        "name-income": "Income",
        "name-expenses": "Expenses",
        "print-stream": "stdout",
        "extension": "beancount",
    }
    assert account_root_names_dflt == m.BC_DEFAULT_ACCOUNT_ROOT_NAMES
    assert dflt_config == m.DFLT_CONFIG

    assert len(m.PrintStream) == 2
    assert m.PrintStream("stdout") == m.PrintStream["STDOUT"]
    assert m.PrintStream("stderr") == m.PrintStream["STDERR"]

    assert isinstance(m.SETTINGS, m.Settings)


def test_print_config_file_address(capsys):
    """Test the print_config_file_address function.

    Also tests invocation from the command line.
    """
    m.print_config_file_path()
    expected_output = (
        f"The beanahead configuration file can be found at:\n\t{m.CONFIG_FILE}\n"
    )
    assert capsys.readouterr().out == expected_output
    set_cl_args("config")
    cli.main()
    assert capsys.readouterr().out == expected_output


def test_print_default_config(dflt_config, capsys):
    m.print_default_config()
    assert capsys.readouterr().out == dflt_config + "\n"


@pytest.fixture
def filepath_mp(monkeypatch, temp_dir) -> abc.Iterator[pathlib.Path]:
    """Mock CONFIG_FILE to a temporary non-existent filepath."""
    path_dir = temp_dir / "not_yet_a_dir"
    monkeypatch.setattr("beanahead.config.CONFIG_DIR", path_dir)
    filepath = path_dir / "config.ini"
    monkeypatch.setattr("beanahead.config.CONFIG_FILE", filepath)
    assert not path_dir.exists()
    assert not filepath.exists()
    yield filepath


def test__write_reset_config(filepath_mp, dflt_config, capsys):
    """Tests _write_config() and reset_config().

    Also tests invocation from the command line.
    """
    path = filepath_mp
    assert not filepath_mp.exists()
    m._write_config()
    assert path.read_text() == dflt_config

    path.write_text("Overwritting config file")
    assert path.read_text() == "Overwritting config file"
    m.reset_config()
    assert path.read_text() == dflt_config

    path.write_text("Overwritting previous config file")
    set_cl_args("config --reset")
    cli.main()
    expected = (
        "The contents of the configuration file have been reset to default values."
    )
    assert capsys.readouterr().out.startswith(expected)
    assert path.read_text() == dflt_config


def test_parse_config(config_dflt, settings_dflt, config_alt, settings_alt):
    """Test parsing of configuration file."""
    # Test valid configuration
    assert m.parse_config(config_dflt) == settings_dflt
    assert m.parse_config(config_alt) == settings_alt

    valid_config = copy.copy(config_dflt)
    # verify leading and trailing whitespace ok and can include . prefix
    valid_config["extension"] = "  .beancount "
    assert m.parse_config(valid_config) == settings_dflt

    # Test invalid keys
    invalid_config = copy.copy(config_dflt)
    invalid_config["invalid_key"] = "value"
    match = (
        "The configuration file includes the following invalid options:"
        " '{'invalid_key'}'.\nThese options will be ignored."
    )
    with pytest.warns(m.ConfigInvalidOptionsWarning, match=match):
        parsed_settings = m.parse_config(invalid_config)
    assert parsed_settings == settings_dflt  # Invalid keys should be ignored

    # Test invalid value for 'print-stream'
    invalid_print_stream = copy.copy(config_dflt)
    invalid_print_stream["print-stream"] = "invalid_stream"
    with pytest.warns(
        m.ConfigInvalidValueWarning,
        match=(
            "'invalid_stream' is not a valid value for the configuration option"
            " print-stream"
        ),
    ):
        parsed_settings = m.parse_config(invalid_print_stream)
    assert parsed_settings == settings_dflt  # default value should have been used
    assert parsed_settings.print_stream == m.PrintStream.STDOUT  # Double check

    # Test invalid value with whitespace within
    invalid_config = copy.copy(config_dflt)
    invalid_config["name-assets"] = "Assets Root"
    with pytest.warns(
        m.ConfigInvalidValueWarning,
        match=(
            "'Assets Root' is not a valid value for the configuration"
            " option name-assets"
        ),
    ):
        parsed_settings = m.parse_config(invalid_config)
    assert parsed_settings == settings_dflt  # Check all as default values
    assert parsed_settings.name_assets == "Assets"  # Double check default value used


@pytest.mark.usefixtures("config_path_mp_alt")
def test_load_config(config_alt):
    """Test loading of configuration section from configuration file."""
    assert m.load_config() == config_alt


@pytest.mark.usefixtures("config_path_mp_alt")
def test_get_settings_from_config(settings_alt):
    """Test loading of settings from configuration file."""
    assert m.get_settings_from_config() == settings_alt


def test_default_print_stream(capsys):
    """Verify default print stream and effect."""
    assert m.SETTINGS.print_stream == m.PrintStream.STDOUT
    assert m.SETTINGS.print_to is sys.stdout
    print("something", file=m.SETTINGS.print_to)
    capture = capsys.readouterr()
    assert capture.out == "something\n"
    assert not capture.err


@pytest.mark.usefixtures("settings_alt_prnt_mp")
def test_alt_print_stream(capsys):
    """Verify alternative print setting and effect."""
    assert m.SETTINGS.print_stream == m.PrintStream.STDERR
    assert m.SETTINGS.print_to is sys.stderr
    print("something", file=m.SETTINGS.print_to)
    capture = capsys.readouterr()
    assert not capture.out
    assert capture.err == "something\n"


def test_account_name_roots(account_root_names_dflt):
    """Tests `get_account_root_names` and `set_account_root_names`."""
    rtrn_dflt = m.get_account_root_names()
    assert rtrn_dflt == account_root_names_dflt

    names = {"name_assets": "Biens", "name_invalid": "Irrelevant"}
    keys = {k.replace("-", "_") for k in m.SETTINGS_DFLTS}
    match = (
        f"'names' parameter can only contain keys: {keys}, although received 'names'"
        " included keys: {'name_invalid'}."
    )
    with pytest.raises(ValueError, match=match):
        m.set_account_root_names(names)
    assert m.get_account_root_names() == account_root_names_dflt  # verify all unchnaged

    names = {"name_assets": "Biens", "name_income": "Ingresos"}
    m.set_account_root_names(names)
    assert m.get_account_root_names() == account_root_names_dflt | names
