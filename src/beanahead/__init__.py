"""beanahead pacakge constructor."""

import contextlib
import sys
from importlib.metadata import version
from pathlib import Path

from . import plugins

__copyright__ = "Copyright (c) 2022 Marcus Read"

# insert plugins directory to path.
path = Path(plugins.__file__).parent
sys.path.insert(0, str(path))


# Resolve version
__version__ = None

with contextlib.suppress(ImportError):
    # get version from installed package
    __version__ = version("beanahead")

if __version__ is None:
    try:
        # if package not installed, get version as set when package built
        from ._version import version
    except Exception:  # noqa: BLE001, S110
        # If package not installed and not built, leave __version__ as None
        pass
    else:
        __version__ = version

del version
