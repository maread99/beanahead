"""Tests package attributes."""

import beanahead


def test_version():
    version = beanahead.__version__
    assert isinstance(version, str)
    assert version
    assert 0 <= int(version[0]) <= 9
