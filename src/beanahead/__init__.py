"""beanahead pacakge constructor."""

from pathlib import Path
import sys

from . import plugins

# insert plugins directory to path.
path = Path(plugins.__file__).parent
sys.path.insert(0, str(path))
