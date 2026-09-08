"""Associative-heterarchical memory package."""

from pathlib import Path
import sys

# Isolated Vanilla RAG lives in repo-root `rag/`, not under src/.
_repo_root = Path(__file__).resolve().parents[2]
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
