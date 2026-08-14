"""Optional desktop GUI for the AH agent.

The package is import-safe without PySide6/VisPy; heavy GUI dependencies are
imported only by :mod:`ah.gui.app` and widget modules.
"""

from .config_store import ApplyMode, ConfigDocument, ConfigEntry
from .graph_state import GraphLayout, GraphVisualMapper, VisualGraph

__all__ = [
    "ApplyMode",
    "ConfigDocument",
    "ConfigEntry",
    "GraphLayout",
    "GraphVisualMapper",
    "VisualGraph",
]
