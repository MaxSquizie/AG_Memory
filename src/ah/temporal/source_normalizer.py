from __future__ import annotations

from datetime import datetime, timezone

from .contracts import TemporalAnchorContext, TemporalCandidate
from .normalizer import TemporalNormalizer as _BaseTemporalNormalizer, _RELATIVE_MARKERS


class TemporalNormalizer(_BaseTemporalNormalizer):
    """Temporal normalizer with strict source-span recognition when no anchor exists.

    ``_BaseTemporalNormalizer.normalize`` deliberately marks an arbitrary phrase as
    unresolved when it merely *contains* a relative marker.  That behavior is useful
    after Perception has already established that the whole phrase is a TIME actant,
    because Integration must fail closed rather than silently invent an anchor.

    Runtime source-span discovery has a different contract: it calls the normalizer
    with an empty ``TemporalAnchorContext`` to ask whether a candidate source span is
    itself a temporal expression.  Treating ``"Я вчера"`` as temporal just because it
    contains ``"вчера"`` makes the preconsumer greedily swallow the subject together
    with TIME.  This adapter separates the two contracts without weakening anchored
    normalization.

    With no anchor, unresolved candidates are retained only when either:

    * the same complete source expression becomes resolved under a synthetic probe
      anchor (for example ``вчера`` or ``вчера в 10:00``); or
    * the complete normalized source is one of the explicitly registered relative
      expressions that the base normalizer intentionally recognizes but cannot yet
      resolve (for example a supported unresolved relative-period form).

    Arbitrary supersets such as ``Я вчера`` or ``примерно вчера после встречи`` are
    therefore not source-level temporal spans.  They remain available to ordinary
    parsing, where a genuinely temporal phrase can still be assigned TIME and later
    validated against the real source/experience anchor.
    """

    _SOURCE_PROBE_ANCHOR = TemporalAnchorContext(
        explicit_anchor=datetime(2000, 1, 2, 12, 0, 0, tzinfo=timezone.utc)
    )

    def normalize(
        self,
        text: str,
        anchors: TemporalAnchorContext | None = None,
    ) -> TemporalCandidate | None:
        context = anchors or TemporalAnchorContext()
        candidate = super().normalize(text, context)
        if candidate is None or candidate.resolved or context.preferred() is not None:
            return candidate

        # Empty-anchor calls are also used as deterministic source-expression
        # recognition.  Probe the *same whole string* under a known anchor: exact
        # relative expressions resolve, while a larger non-temporal span containing
        # a marker still falls through as unresolved.
        probe = super().normalize(text, self._SOURCE_PROBE_ANCHOR)
        if probe is not None and probe.resolved:
            return candidate

        folded = " ".join(text.strip().split()).casefold().replace("ё", "е")
        if folded in _RELATIVE_MARKERS:
            return candidate
        return None
