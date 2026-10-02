from __future__ import annotations

from types import SimpleNamespace
from threading import RLock

import pytest

from ah.agent import InteractionContext
from ah.config import ContextSettings, IgnitionSettings, LifecycleSettings, WorkspaceSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.documents import DocumentProcessingError, DocumentProcessor
from ah.ignition import IgnitionEngine
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, Domain, Property
from ah.projection import AgentContext, ContextProjector


def _entity(core: AHCore, name: str, domain: Domain = Domain.C):
    item = core.add_entity(domain, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def _fact(core: AHCore, predicate: str, subject):
    symbol = core.ensure_abstract_symbol(predicate)
    template = core.add_template(Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT,))
    node, _ = core.add_hypernode(
        Domain.C,
        core.ref(template.uid),
        {ActantRole.SUBJECT: subject},
        0.4,
    )
    return core.ref(node.uid)


def _services():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = _entity(core, "Пользователь", Domain.P)
    roots = (
        _fact(core, "запуститься", _entity(core, "Процесс A")),
        _fact(core, "продолжиться", _entity(core, "Процесс B")),
        _fact(core, "завершиться", _entity(core, "Процесс C")),
    )
    core.add_link("CAUSE", roots[0], roots[1], 0.5)
    core.add_link("FOLLOW", roots[1], roots[2], 0.5)
    ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text="RAW DOCUMENT MUST NOT ENTER SUMMARY CONTEXT",
        speaker_ref=user,
        semantic_refs=roots,
        context=InteractionContext(user_ref=user),
        speech_act_kinds=("ASSERTION",),
        source_ref="doc:continuation",
        batch_kind="DOCUMENT",
    )
    ignition = IgnitionEngine(
        core,
        IgnitionSettings(),
        WorkspaceSettings(threshold=0.35),
        LifecycleSettings(gc_enabled=False),
    )
    return SimpleNamespace(
        core=core,
        ignition=ignition,
        projector=ContextProjector(core, ContextSettings(max_tokens=4096)),
        operation_lock=RLock(),
        agent=None,
    ), roots


class CapturingAgent:
    def __init__(self) -> None:
        self.contexts: list[AgentContext] = []

    def respond(self, context: AgentContext) -> str:
        self.contexts.append(context)
        if "[DOCUMENT PARTIALS]" in context.rendered:
            return "Итог по документу"
        return f"Частичный итог {len(self.contexts)}"


def test_summary_cursor_visits_every_primary_once_and_only_carries_past_overlap():
    services, roots = _services()
    agent = CapturingAgent()
    services.agent = agent

    result = DocumentProcessor(services).summarize(
        "doc:continuation",
        request="Перескажи источник.",
        max_primary_roots=1,
        max_slices=4,
        budget_tokens=512,
    )

    assert result.text == "Итог по документу"
    assert result.stop_reason == "source_complete"
    assert tuple(item.cursor_start for item in result.slice_diagnostics) == (0, 1, 2)
    assert tuple(item.cursor_end for item in result.slice_diagnostics) == (1, 2, 3)
    assert tuple(uid for item in result.slice_diagnostics for uid in item.primary_refs) == tuple(
        ref.uid for ref in roots
    )
    assert result.slice_diagnostics[0].overlap_refs == ()
    assert result.slice_diagnostics[1].overlap_refs == (roots[0].uid,)
    assert roots[2].uid not in result.slice_diagnostics[1].overlap_refs
    assert result.slice_diagnostics[2].done is True
    assert len(agent.contexts) == 4  # three AH slices + one controlled aggregation
    assert all("RAW DOCUMENT MUST NOT ENTER SUMMARY CONTEXT" not in item.rendered for item in agent.contexts)
    assert "[DOCUMENT PARTIALS]" in agent.contexts[-1].rendered


def test_summary_cursor_sequence_and_projection_are_deterministic_across_fresh_runs():
    first_services, _ = _services()
    second_services, _ = _services()
    first_services.agent = CapturingAgent()
    second_services.agent = CapturingAgent()

    first = DocumentProcessor(first_services).summarize(
        "doc:continuation", max_primary_roots=1, max_slices=4, budget_tokens=512
    )
    second = DocumentProcessor(second_services).summarize(
        "doc:continuation", max_primary_roots=1, max_slices=4, budget_tokens=512
    )

    assert [
        (item.cursor_start, item.cursor_end, item.primary_refs, item.overlap_refs)
        for item in first.slice_diagnostics
    ] == [
        (item.cursor_start, item.cursor_end, item.primary_refs, item.overlap_refs)
        for item in second.slice_diagnostics
    ]
    assert [item.rendered for item in first_services.agent.contexts] == [
        item.rendered for item in second_services.agent.contexts
    ]


def test_summary_fails_closed_when_max_slices_prevents_source_completion():
    services, _ = _services()
    services.agent = CapturingAgent()

    with pytest.raises(DocumentProcessingError, match="max_slices=2"):
        DocumentProcessor(services).summarize(
            "doc:continuation",
            max_primary_roots=1,
            max_slices=2,
            budget_tokens=512,
        )

    assert len(services.agent.contexts) == 2
