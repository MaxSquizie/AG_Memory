from __future__ import annotations

import inspect

from ah.agent.orchestrator import AgentOrchestrator
from ah.inference import TurnGoalBuilder


def test_orchestrator_has_no_lexical_prove_dispatch():
    source = inspect.getsource(AgentOrchestrator)
    assert "_PROVE_COMMAND_FORMS" not in source
    assert "behavior:PROVE" not in source
    assert "доказать" not in source.casefold()
    assert "prove" not in source.casefold()


def test_turn_goal_builder_contract_is_semantic_not_lexical():
    # Public TurnGoalBuilder composes several semantic compilers through its MRO;
    # inspect the complete production chain rather than only the outer extension.
    source = "\n".join(
        inspect.getsource(cls)
        for cls in TurnGoalBuilder.__mro__
        if cls.__module__.startswith("ah.inference")
    )
    assert "semantic_scope" in source
    assert '"EMBEDDED"' in source
    assert "unresolved_queries" in source
