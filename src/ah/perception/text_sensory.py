from __future__ import annotations

from dataclasses import dataclass
import re

from ah.core import AHCore
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import Ref

from .morphology import Morphology, build_morphology, stable_normal_form


# Unicode word tokens, allowing an internal hyphen/apostrophe. Numbers are sensory
# tokens too because they can later resolve into semantic values/entities.
_TOKEN_RE = re.compile(r"[^\W_]+(?:[-'][^\W_]+)*", re.UNICODE)


@dataclass(frozen=True, slots=True)
class TextSensoryResult:
    tokens: tuple[str, ...]
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

    def _lexical_form(self, token: str) -> str:
        """Return a deterministic lexical identity for primary-symbol reuse.

        S stores ordinary forms rather than a dedicated lemma field.  Morphology is
        therefore used only as an index key: the observed surface form is added to
        the same S as its highest-ranked normal form.  This keeps inflectional
        variants such as ``Мария/Марии/Марию`` inside one lexical symbol while
        preserving the exact observed token in R_text.
        """
        analyses = self.morphology.analyze_all(token)
        normal = stable_normal_form(analyses)
        if not normal:
            return token
        if token[:1].isupper():
            normal = normal[:1].upper() + normal[1:]
        return normal

    def process(self, text: str) -> TextSensoryResult:
        tokens = tuple(match.group(0) for match in _TOKEN_RE.finditer(text))
        refs: list[Ref] = []
        seeds: list[ActivationSeedRequest] = []
        for token in tokens:
            lexical = self._lexical_form(token)
            symbol = self.core.ensure_abstract_symbol(lexical)
            if token not in symbol.forms:
                symbol = self.core.add_symbol_form(symbol.uid, token)
            ref = self.core.ref(symbol.uid)
            refs.append(ref)
            # One seed per observed occurrence. Repetition in the same sensory input
            # can therefore contribute more z without changing semantic w directly.
            seeds.append(ActivationSeedRequest(ref, SeedReason.SENSORY_SYMBOL))
        return TextSensoryResult(tokens, tuple(refs), tuple(seeds))
