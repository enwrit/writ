"""enwrit (writ) -- Agent instruction management CLI.

Compose, port, and score AI agent configs across tools, projects, and devices.
"""

from importlib.metadata import version as _pkg_version

try:
    __version__ = _pkg_version("enwrit")
except Exception:
    __version__ = "0.0.0"
