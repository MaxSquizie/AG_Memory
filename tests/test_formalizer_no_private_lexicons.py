# -*- coding: utf-8 -*-
"""Guard: NO private examples / per-word dictionaries in the formalizer (full ban).

Project invariant (two-tier rule): structural rules are allowed when *declared +
corpus-tested*; **lexical-semantic mappings** (a specific content word -> a meaning,
role, operator type, construction label) are FORBIDDEN except through a *sanctioned,
explicitly-declared language resource*. This test mechanically enforces that ban on the
new architecture package ``src/ah/formalizer``:

* It scans every module for the *signature* of a lexical-semantic map — a Cyrillic string
  literal used as a **dict key** mapped to a value (e.g. ``{"каждый": "EVERY"}`` or
  ``{("ADJF", "каждый"): "EVERY"}``). Functional closed sets (``{"и","а","но"}``), finite
  grammar constants, morphology rules and test fixtures do NOT carry this signature.
* A match is legal ONLY if it belongs to a variable registered in ``SANCTIONED_LEXICONS``
  below — the explicit declaration channel. Adding a new legitimate lexicon therefore
  requires a deliberate entry here (a declared resource), never an ad-hoc inline hack.

This is additive: it cannot regress existing behaviour; it only fails when someone
introduces an *undeclared* private dictionary into the formalizer going forward.
"""
from __future__ import annotations

import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_FORMALIZER_ROOT = os.path.normpath(
    os.path.join(_HERE, "..", "src", "ah", "formalizer")
)

# The ONLY sanctioned lexical-semantic resources in the formalizer. Each entry is a
# (module_basename, variable_name) pair: a Cyrillic-key->value map is legal only when it
# defines one of these declared, versioned resources. To add a new lexicon you MUST add
# it here first — that act IS the declaration the architecture requires.
SANCTIONED_LEXICONS = {
    ("composition.py", "CONNECTIVES_V1"),   # [connectives_v1] subordinator connective pattern
    ("composition.py", "SCOPE_LEXICON_V1"),  # [scope_lexicon_v1] (pos, lemma) -> operator type
}

# A Cyrillic string literal used as a dict key followed by ':' — the lexical-semantic-map
# signature. Covers plain keys ("слово": ...) and tuple keys (("POS", "слово"): ...).
_KEY_RE = re.compile(
    r"""(?:"[а-яА-ЯёЁ][^"]*"|'[^']*[а-яА-ЯёЁ][^']*')\s*\)?\s*:"""
)


def _strip_docstrings_and_comments(src: str) -> str:
    """Remove triple-quoted strings and # comments so prose like ``('у меня'):`` in a
    docstring cannot masquerade as a lexical map."""
    src = re.sub(r'"""[\s\S]*?"""', "", src)
    src = re.sub(r"'''[\s\S]*?'''", "", src)
    lines = []
    for line in src.splitlines():
        # drop full-line comments; keep code (inline trailing comments are harmless here
        # because a comment cannot contain the key->value signature we look for).
        if line.lstrip().startswith("#"):
            continue
        lines.append(line)
    return "\n".join(lines)


def _owning_variable(lines: list[str], idx: int) -> str | None:
    """Walk upward from a hit to the nearest top-level ``NAME =`` / ``NAME:`` assignment."""
    for j in range(idx, -1, -1):
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*(?::[^=]+)?=", lines[j])
        if m:
            return m.group(1)
        # stop at the previous top-level statement boundary (a non-indented line that is
        # not a continuation of the current literal).
        stripped = lines[j].strip()
        if j < idx and stripped and not lines[j][0].isspace():
            break
    return None


class NoPrivateLexiconsTests(unittest.TestCase):
    def test_formalizer_has_no_undeclared_lexical_semantic_maps(self) -> None:
        self.assertTrue(
            os.path.isdir(_FORMALIZER_ROOT),
            f"formalizer package not found at {_FORMALIZER_ROOT}",
        )
        violations: list[str] = []
        for dirpath, _dirs, files in os.walk(_FORMALIZER_ROOT):
            for fn in sorted(files):
                if not fn.endswith(".py"):
                    continue
                path = os.path.join(dirpath, fn)
                rel = os.path.relpath(path, _HERE).replace(os.sep, "/")
                src = open(path, encoding="utf-8").read()
                code = _strip_docstrings_and_comments(src)
                lines = code.splitlines()
                for i, line in enumerate(lines):
                    if not _KEY_RE.search(line):
                        continue
                    var = _owning_variable(lines, i)
                    key = (fn, var)
                    if key in SANCTIONED_LEXICONS:
                        continue
                    violations.append(
                        f"{rel}:{i + 1} [{var}] {line.strip()[:90]}"
                    )
        self.assertEqual(
            violations,
            [],
            "Undeclared private dictionary / lexical-semantic map found in the formalizer.\n"
            "Per-word semantic knowledge is forbidden; route it through a declared, versioned\n"
            "language resource and register that variable in SANCTIONED_LEXICONS:\n  - "
            + "\n  - ".join(violations),
        )

    def test_sanctioned_lexicons_are_actually_declared(self) -> None:
        """The allowlist must not drift: every sanctioned entry must exist as a real,
        Cyrillic-keyed map in its module (guards against a stale/typo'd whitelist)."""
        for fn, var in SANCTIONED_LEXICONS:
            path = os.path.join(_FORMALIZER_ROOT, fn)
            self.assertTrue(os.path.isfile(path), f"missing sanctioned resource file {fn}")
            code = _strip_docstrings_and_comments(open(path, encoding="utf-8").read())
            lines = code.splitlines()
            found = False
            for i, line in enumerate(lines):
                if re.match(rf"^{re.escape(var)}\s*(?::[^=]+)?=", line) and _KEY_RE.search(
                    "\n".join(lines[i : i + 6])
                ):
                    found = True
                    break
            self.assertTrue(found, f"sanctioned lexicon {var} in {fn} not found / not a map")


if __name__ == "__main__":
    unittest.main()
