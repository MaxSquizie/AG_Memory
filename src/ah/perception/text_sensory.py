from __future__ import annotations

from dataclasses import dataclass
import re

from ah.core import AHCore
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import Ref

from .morphology import Morphology, build_morphology, material_analyses


# Unicode word tokens, allowing an internal hyphen/apostrophe. Numbers are sensory
# tokens too because they can later resolve into semantic values/entities.
_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class TextSensoryResult:
    tokens: tuple[str, ...]
    # Candidate lattice aligned with ``tokens``.  One surface token can activate
    # several lexical S nodes; an empty tuple means that no canonical lexeme is
    # known yet and creation is deferred until semantic perception can resolve it.
    candidate_refs_by_token: tuple[tuple[Ref, ...], ...]
    symbol_refs: tuple[Ref, ...]
    activation_seeds: tuple[ActivationSeedRequest, ...]


class TextSensoryService:
    """Text primary-symbol recognition/creation before semantic perception.

    This layer does not decide entity identity or truth. It only maps observed text
    forms to S and emits external sensory stimulation requests.
    """

    def __init__(self, core: AHCore, morphology: Morphology | None = None) -> None:
        self.core = core
        self.morphology = morphology or build_morphology("auto")

    def _candidate_symbols(self, token: str):
        """Build a lexical lattice without choosing one morphology reading.

        Surface lookup is always included.  Morphology may *retrieve* additional
        already-known paradigms through every material normal form, but analyser
        score/order never chooses one canonical S and this layer never extends or
        creates S.  Unknown lexical identity is intentionally left unresolved for
        the semantic perception/integration boundary.
        """
        found = {
            symbol.uid: symbol
            for symbol in self.core.store.find_symbols_by_form(token)
        }
        for analysis in material_analyses(self.morphology.analyze_all(token)):
            normal = analysis.normal_form.strip()
            if not normal:
                continue
            for symbol in self.core.store.find_symbols_by_form(normal):
                found[symbol.uid] = symbol
        return tuple(found[uid] for uid in sorted(found))

    def process(self, text: str) -> TextSensoryResult:
        tokens = tuple(match.group(0) for match in _TOKEN_RE.finditer(text))
        lattice: list[tuple[Ref, ...]] = []
        refs: list[Ref] = []
        seeds: list[ActivationSeedRequest] = []
        for token in tokens:
            token_refs = tuple(
                self.core.ref(symbol.uid)
                for symbol in self._candidate_symbols(token)
            )
            lattice.append(token_refs)
            for ref in token_refs:
                refs.append(ref)
                # One seed per candidate per observed occurrence.  Homography may
                # therefore stimulate several lexical hypotheses, but sensory input
                # does not decide which one is semantically intended.
                seeds.append(ActivationSeedRequest(ref, SeedReason.SENSORY_SYMBOL))
        return TextSensoryResult(tokens, tuple(lattice), tuple(refs), tuple(seeds))
