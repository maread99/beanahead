"""beanahead pacakge constructor."""

from importlib.metadata import version
from pathlib import Path
import sys

from . import plugins

__copyright__ = "Copyright (c) 2022 Marcus Read"

# insert plugins directory to path.
path = Path(plugins.__file__).parent
sys.path.insert(0, str(path))


# Resolve version
__version__ = None

try:
    # get version from installed package
    __version__ = version("beanahead")
except ImportError:
    pass

if __version__ is None:
    try:
        # if package not installed, get version as set when package built
        from ._version import version
    except Exception:
        # If package not installed and not built, leave __version__ as None
        pass
    else:
        __version__ = version

del version
