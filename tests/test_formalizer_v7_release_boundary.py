"""The product wrapper reports an absent release before dereferencing it."""
from types import SimpleNamespace

import pytest

from ah.agent.interaction_context import InteractionContext
from ah.perception.llm_parser import (
    LLMPerceptionService, LLMPerceptionSettings, PerceptionParseError,
)


def test_native_perception_without_release_has_typed_failure():
    formalizer = SimpleNamespace(native_available=True, _release=None)
    service = LLMPerceptionService(None, LLMPerceptionSettings(), formalizer=formalizer)
    with pytest.raises(PerceptionParseError, match="RESOURCE_MISSING"):
        service.perceive("Мария спит.", InteractionContext())
