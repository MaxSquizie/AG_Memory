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
    source = inspect.getsource(TurnGoalBuilder)
    assert "semantic_scope" in source
    assert '"EMBEDDED"' in source
    assert "unresolved_queries" in source
