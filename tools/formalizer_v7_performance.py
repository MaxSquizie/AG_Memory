#!/usr/bin/env python3
"""CLI for the package-owned, prompt-free oracle timing reducer."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if __package__ in {None, ""}:
    sys.path.insert(0, str(ROOT / "src"))

from ah.gui.oracle_performance import SCHEMA, format_performance, main, summarize_progress

__all__ = ["SCHEMA", "format_performance", "main", "summarize_progress"]

if __name__ == "__main__":
    raise SystemExit(main())
