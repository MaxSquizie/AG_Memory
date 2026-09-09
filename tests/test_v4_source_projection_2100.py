from __future__ import annotations

from pathlib import Path

import pytest

from ah.agent import InteractionContext
from ah.config import (
    ContextSettings,
    IgnitionSettings,
    IntegrationSettings,
    LifecycleSettings,
    PersistenceSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, JsonPersistence, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.integration.contracts import ActivationSeedRequest, SeedReason
from ah.integration.experience_mapper import ExperienceMapper
from ah.model import ActantRole, Domain, Property
from ah.projection import (
    ContextProjector,
    ProjectionBudgetExceeded,
    SourceScopeActivator,
    SourceScopeResolver,
    SourceScopedContextService,
)


def entity(core: AHCore, name: str, domain: Domain = Domain.C):
    item = core.add_entity(domain, {"name": Property("name", name, "str")})
    return core.ref(item.uid)


def fact(core: AHCore, predicate: str, subject, obj=None):
    symbol = core.ensure_abstract_symbol(predicate)
    roles = (ActantRole.SUBJECT,) if obj is None else (ActantRole.SUBJECT, ActantRole.OBJECT)
    template = core.add_template(Domain.C, core.ref(symbol.uid), roles)
    actants = {ActantRole.SUBJECT: subject}
    if obj is not None:
        actants[ActantRole.OBJECT] = obj
    node, _ = core.add_hypernode(Domain.C, core.ref(template.uid), actants, 0.4)
    return core.ref(node.uid)


def document_memory():
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = entity(core, "Пользователь", Domain.P)
    first_subject = entity(core, "Датчик")
    alarm = entity(core, "Тревога")
    staff = entity(core, "Персонал")
    first = fact(core, "обнаружить", first_subject, alarm)
    second = fact(core, "эвакуироваться", staff)
    core.add_link("CAUSE", first, second, 0.5)

    unrelated_subject = entity(core, "Кот")
    unrelated = fact(core, "спать", unrelated_subject)

    context = InteractionContext(user_ref=user)
    mapper = ExperienceMapper(core, event_weight=0.3, follow_weight=0.2)
    experience = mapper.record_turn(
        source_text="TOP SECRET RAW DOCUMENT: датчик вызвал тревогу; персонал эвакуировался.",
        speaker_ref=user,
        semantic_refs=(first, second),
        context=context,
        speech_act_kinds=("ASSERTION",),
        source_ref="doc:incident-1",
        batch_kind="DOCUMENT",
    )
    return core, context, experience.event_ref, first, second, unrelated


def ignition_for(core: AHCore) -> IgnitionEngine:
    return IgnitionEngine(
        core,
        IgnitionSettings(),
        WorkspaceSettings(threshold=0.35),
        LifecycleSettings(gc_enabled=False),
    )


def test_document_occurrence_keeps_source_handle_but_not_raw_text_in_h():
    core, _context, event_ref, _first, _second, _unrelated = document_memory()
    event = core.store.get_hypernode(event_ref.uid)
    assert event.meta["source_ref"] == "doc:incident-1"
    assert event.meta["batch_kind"] == "DOCUMENT"
    assert "text" not in event.properties


def test_source_scope_resolves_semantic_roots_through_rebuildable_index_without_domain_scan(monkeypatch):
    core, _context, event_ref, first, second, _unrelated = document_memory()

    def forbidden(*_args, **_kwargs):
        raise AssertionError("source scope must not enumerate a whole AH domain")

    monkeypatch.setattr(core.store, "elements", forbidden)
    monkeypatch.setattr(core.store, "all_elements", forbidden)
    monkeypatch.setattr(core.store, "all_uids", forbidden)
    monkeypatch.setattr(core.store, "links", forbidden)

    scope = SourceScopeResolver(core).resolve("doc:incident-1")
    assert tuple(ref.uid for ref in scope.experience_refs) == (event_ref.uid,)
    assert tuple(ref.uid for ref in scope.semantic_roots) == (first.uid, second.uid)


def test_source_scope_activation_and_projection_are_ah_only_and_preserve_cause(monkeypatch):
    core, _context, _event_ref, first, second, unrelated = document_memory()
    ignition = ignition_for(core)

    # Warm unrelated memory must not leak into a source-scoped summary context.
    ignition.apply_seed_requests((ActivationSeedRequest(unrelated, SeedReason.QUERY_RECALL),))
    ignition.tick(include_pacemaker=False)

    activation = SourceScopeActivator(core, ignition).activate("doc:incident-1", settle_ticks=1)
    assert {ref.uid for ref in activation.seeded_refs} == {first.uid, second.uid}

    def forbidden(*_args, **_kwargs):
        raise AssertionError("source-scoped projection must not broad-scan AH")

    monkeypatch.setattr(core.store, "elements", forbidden)
    monkeypatch.setattr(core.store, "all_elements", forbidden)
    monkeypatch.setattr(core.store, "all_uids", forbidden)
    monkeypatch.setattr(core.store, "links", forbidden)

    context = ContextProjector(core, ContextSettings(max_tokens=4096)).project(
        "Кратко перескажи источник.",
        activation.workspace_after,
        source_scope=activation.source_scope,
    )

    assert context.source_scope_ref == "doc:incident-1"
    assert context.estimated_tokens > 0
    assert "TOP SECRET RAW DOCUMENT" not in context.rendered
    assert "Кот" not in context.rendered
    assert "спать" not in context.rendered
    assert "обнаружить" in context.rendered
    assert "эвакуироваться" in context.rendered
    assert "CAUSE" in context.rendered


def test_legacy_document_event_text_is_never_projected_even_if_it_becomes_active():
    core, _context, event_ref, first, second, _unrelated = document_memory()
    event = core.store.get_hypernode(event_ref.uid)
    legacy = type(event)(
        event.uid,
        event.weight,
        event.template,
        event.actants,
        {"text": Property("text", "LEGACY RAW DOCUMENT MUST NOT LEAK", "str")},
        event.meta,
    )
    core.edit_element(Domain.H, legacy)

    context = ContextProjector(core, ContextSettings(max_tokens=4096)).project(
        "Что известно?", (event_ref, first, second)
    )
    assert "LEGACY RAW DOCUMENT MUST NOT LEAK" not in context.rendered


def test_projection_budget_fails_closed_instead_of_truncating_or_using_raw_chunks():
    core, _context, _event_ref, _first, _second, _unrelated = document_memory()
    with pytest.raises(ProjectionBudgetExceeded) as caught:
        ContextProjector(core, ContextSettings(max_tokens=4096)).project(
            "очень длинный запрос " * 50,
            (),
            budget_tokens=8,
        )
    assert caught.value.estimated_tokens > caught.value.budget_tokens
    assert "raw-chunk" in str(caught.value)


def test_source_scope_index_rebuilds_after_persistence_reload(tmp_path: Path):
    core, _context, event_ref, first, second, _unrelated = document_memory()
    path = tmp_path / "ah.json"
    persistence = JsonPersistence(
        path,
        PersistenceSettings(
            enabled=True,
            load_on_start=True,
            autosave_every_ticks=100,
            save_runtime_state=True,
            save_pending_impulses=True,
        ),
    )
    persistence.save(core)
    loaded = persistence.load(uid_generator=SequentialUidGenerator()).core
    scope = SourceScopeResolver(loaded).resolve("doc:incident-1")
    assert tuple(ref.uid for ref in scope.experience_refs) == (event_ref.uid,)
    assert tuple(ref.uid for ref in scope.semantic_roots) == (first.uid, second.uid)


def test_source_scoped_context_service_composes_activation_and_projection():
    core, _context, _event_ref, first, second, unrelated = document_memory()
    ignition = ignition_for(core)
    projector = ContextProjector(core, ContextSettings(max_tokens=4096))
    service = SourceScopedContextService(SourceScopeActivator(core, ignition), projector)

    result = service.build(
        "Перескажи документ.",
        "doc:incident-1",
        settle_ticks=1,
    )
    assert result.context.source_scope_ref == "doc:incident-1"
    assert {ref.uid for ref in result.activation.seeded_refs} == {first.uid, second.uid}
    assert unrelated.uid not in {ref.uid for ref in result.activation.seeded_refs}
    assert "TOP SECRET RAW DOCUMENT" not in result.context.rendered


def test_complete_source_projection_is_index_bounded_explicitly_compacted_and_deterministic(monkeypatch):
    core = AHCore(uid_generator=SequentialUidGenerator())
    user = entity(core, "Пользователь", Domain.P)
    roots = tuple(
        fact(core, "описывать", entity(core, f"Раздел {index} с подробным названием"))
        for index in range(8)
    )
    for index, target in enumerate(roots[1:], start=1):
        core.add_link(
            ("BEFORE", "AFTER", "OVERLAP", "CAUSE")[index % 4],
            roots[0],
            target,
            0.4,
        )
    ExperienceMapper(core, event_weight=0.3, follow_weight=0.2).record_turn(
        source_text="RAW SOURCE MUST NEVER ENTER THE MODEL",
        speaker_ref=user,
        semantic_refs=roots,
        context=InteractionContext(user_ref=user),
        speech_act_kinds=("ASSERTION",),
        source_ref="doc:compact",
        batch_kind="DOCUMENT",
    )
    ignition = IgnitionEngine(
        core,
        IgnitionSettings(),
        WorkspaceSettings(threshold=10.0),
        LifecycleSettings(gc_enabled=False),
    )
    service = SourceScopedContextService(
        SourceScopeActivator(core, ignition),
        ContextProjector(core, ContextSettings(max_tokens=4096)),
    )

    def forbidden(*_args, **_kwargs):
        raise AssertionError("complete source context must stay on source/adjacency indexes")

    monkeypatch.setattr(core.store, "elements", forbidden)
    monkeypatch.setattr(core.store, "all_elements", forbidden)
    monkeypatch.setattr(core.store, "all_uids", forbidden)
    monkeypatch.setattr(core.store, "links", forbidden)

    first = service.build_complete_source(
        "Сожми документ.", "doc:compact", budget_tokens=70
    ).context
    second = service.build_complete_source(
        "Сожми документ.", "doc:compact", budget_tokens=70
    ).context
    assert first.rendered == second.rendered
    assert first.estimated_tokens <= 70
    assert "сжат детерминированно" in first.rendered
    assert "RAW SOURCE MUST NEVER ENTER THE MODEL" not in first.rendered
    assert roots[0].uid in {ref.uid for ref in first.source_workspace_refs}
