from __future__ import annotations

from dataclasses import dataclass
import re

from ah.core import AHCore
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.model import Ref


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

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def process(self, text: str) -> TextSensoryResult:
        tokens = tuple(match.group(0) for match in _TOKEN_RE.finditer(text))
        refs: list[Ref] = []
        seeds: list[ActivationSeedRequest] = []
        for token in tokens:
            symbol = self.core.ensure_abstract_symbol(token)
            ref = self.core.ref(symbol.uid)
            refs.append(ref)
            # One seed per observed occurrence. Repetition in the same sensory input
            # can therefore contribute more z without changing semantic w directly.
            seeds.append(ActivationSeedRequest(ref, SeedReason.SENSORY_SYMBOL))
        return TextSensoryResult(tokens, tuple(refs), tuple(seeds))
