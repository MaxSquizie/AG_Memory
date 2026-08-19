from __future__ import annotations

from contextlib import nullcontext
from dataclasses import asdict, dataclass, field
from datetime import datetime
import json
from pathlib import Path
from threading import RLock
from time import perf_counter

from ah.config import (
    IgnitionSettings,
    InferenceSettings,
    LifecycleSettings,
    WorkspaceSettings,
)
from ah.core import AHCore, SequentialUidGenerator
from ah.ignition import IgnitionEngine
from ah.inference import (
    AllOfGoal,
    CauseEntailmentGoal,
    GoalSpec,
    IgnitionInferenceAttention,
    InferenceEngine,
    InferenceQuery,
    LogicalStatus,
    RelationGoal,
    StopReason,
)
from ah.model import Domain, Property, Ref
from .graph_dump import GraphInspector, GraphSnapshot
from .inference_proof import ProofCheck, ProofChainSnapshot, ProofSnapshotBuilder


RUNS_DIRNAME = "m2_runs"
DEFAULT_STRESS_AH_UIDS = 150_000


@dataclass(frozen=True, slots=True)
class M2AcceptanceCaseResult:
    scenario: str
    relation: str
    goal_depth: int
    status: str
    stop_reason: str
    logical_depth: int
    passed: bool
    purity_control: bool
    workspace_before_count: int
    workspace_after_count: int
    path_cold_before: bool
    path_excited_after: bool
    tail_inactive_after: bool
    excitation_changed: bool
    trace_uids: tuple[str, ...]
    expected_trace_uids: tuple[str, ...]
    attention_focus_uids: tuple[str, ...]
    expected_attention_focus_uids: tuple[str, ...]
    tail_absent_from_trace: bool
    foreign_absent_from_trace: bool
    foreign_absent_from_attention: bool
    elapsed_ms: float
    diagnostics: tuple[str, ...] = ()
    proof: ProofChainSnapshot | None = None


@dataclass(frozen=True, slots=True)
class M2AcceptanceRunResult:
    total: int
    passed: int
    failed: int
    base_mode: str
    ah_uids: int
    cold_uids_added: int
    initial_workspace_count: int
    final_workspace_count: int
    elapsed_seconds: float
    output_dir: Path
    cases: tuple[M2AcceptanceCaseResult, ...]
    # Runtime-only frozen view for the GUI canvas browser. It is intentionally not
    # written into result.json: the JSON already contains every proof, while this
    # snapshot may contain 150k+ diagnostic nodes.
    sandbox_snapshot: GraphSnapshot | None = field(default=None, repr=False, compare=False)


class _Fixture:
    def __init__(
        self,
        *,
        core: AHCore,
        inference: InferenceSettings,
        ignition: IgnitionSettings,
        workspace: WorkspaceSettings,
        lifecycle: LifecycleSettings,
        ignition_snapshot=None,
    ) -> None:
        self.core = core
        self.engine = InferenceEngine(core, inference)
        self.ignition = IgnitionEngine(core, ignition, workspace, lifecycle)
        if ignition_snapshot is not None:
            self.ignition.restore_snapshot(ignition_snapshot)
        self.attention = IgnitionInferenceAttention(self.ignition)
        self._label_counter = 0

    def entity(self, domain: Domain, name: str) -> Ref:
        obj = self.core.add_entity(
            domain,
            properties={"name": Property("name", name, "str")},
            meta={"m2_fixture": True},
        )
        return self.core.ref(obj.uid)

    def fact(self, domain: Domain, label: str) -> Ref:
        self._label_counter += 1
        # M2 identity is carried by canonical UID, not by an opaque diagnostic
        # spelling. Keep proposition text human-readable so the exact same proof
        # can be audited visually without sacrificing deterministic UID checks.
        symbol = self.core.ensure_abstract_symbol(label)
        template = self.core.add_template(domain, self.core.ref(symbol.uid), ())
        node, _ = self.core.add_hypernode(
            domain,
            self.core.ref(template.uid),
            {},
            0.4,
            meta={"m2_fixture": True},
            deduplicate=False,
            count_occurrence=False,
        )
        return self.core.ref(node.uid)

    def add_chain(self, relation_id: str, nodes: list[Ref]):
        return [
            self.core.add_link(relation_id, nodes[index], nodes[index + 1], 0.4)
            for index in range(len(nodes) - 1)
        ]

    def add_dead_branches(
        self,
        relation_id: str,
        nodes: list[Ref],
        *,
        domain: Domain,
        use_facts: bool,
        fanout: int,
    ) -> tuple[Ref, ...]:
        distractors: list[Ref] = []
        # Do not branch from the final tail endpoint. Every distractor is a dead end,
        # so bounded reverse goal-relevance can reject it without semantic expansion.
        for depth, source in enumerate(nodes[:-1]):
            for branch in range(fanout):
                label = f"Ложная ветвь {relation_id}: от шага {depth}, вариант {branch + 1}"
                target = self.fact(domain, label) if use_facts else self.entity(domain, label)
                self.core.add_link(relation_id, source, target, 0.4)
                distractors.append(target)
        return tuple(distractors)

    def excite(self, refs: tuple[Ref, ...]) -> None:
        for ref in refs:
            self.attention.focus(ref, logical_depth=0)
        self.attention.begin()



_SCENARIO_TITLES = {
    "cause_alpha": "Пожарная причинная цепочка",
    "cause_beta": "Обработка запроса",
    "follow_episode": "Последовательность эпизода",
    "isa_concepts": "Таксономия",
    "cross_left": "Независимая левая причинная цепь",
    "cross_right": "Независимая правая причинная цепь",
    "branch_cause_cold": "CAUSE с холодными ложными ветвями",
    "branch_cause_warm": "CAUSE с заранее активными ложными ветвями",
    "branch_follow_warm": "FOLLOW с заранее активными ложными ветвями",
    "branch_isa_cold": "IS-A с холодными ложными ветвями",
    "mixed_cf_d2": "Смешанный вывод CAUSE → FOLLOW",
    "mixed_ci_d2": "Смешанный вывод CAUSE → IS-A",
    "mixed_fi_d2": "Смешанный вывод FOLLOW → IS-A",
    "mixed_cfi_d3": "Смешанный вывод CAUSE → FOLLOW → IS-A",
    "mixed_cfi_d4": "Смешанный вывод C/F/IS-A depth 4",
    "mixed_cfi_d5": "Смешанный вывод C/F/IS-A depth 5",
    "mixed_cfi_d6_cold": "Смешанный вывод C/F/IS-A depth 6 cold",
    "mixed_cfi_d6_warm": "Смешанный вывод C/F/IS-A depth 6 warm branches",
}

_SCENARIO_SEQUENCES = {
    "cause_alpha": (
        "Датчик обнаружил дым",
        "Система активировала тревогу",
        "Охрана получила сигнал",
        "Охранник начал проверку помещения",
        "Пожар подтверждён",
        "Началась эвакуация",
        "Люди покинули опасную зону",
        "Пожарные получили вызов",
        "Инцидент локализован",
    ),
    "cause_beta": (
        "Сервис получил запрос",
        "Запрос прошёл валидацию",
        "Задача поставлена в очередь",
        "Воркер взял задачу",
        "Данные обработаны",
        "Результат сохранён",
        "Клиент получил уведомление",
        "Метрики записаны",
        "Запрос закрыт",
    ),
    "follow_episode": (
        "Пользователь вошёл в комнату",
        "Пользователь включил свет",
        "Пользователь открыл шкаф",
        "Пользователь взял документ",
        "Пользователь прочитал документ",
        "Пользователь сделал заметку",
        "Пользователь убрал документ",
        "Пользователь выключил свет",
        "Пользователь вышел из комнаты",
    ),
    "isa_concepts": (
        "овчарка",
        "собака",
        "псовое",
        "хищное млекопитающее",
        "млекопитающее",
        "позвоночное",
        "животное",
        "эукариот",
        "организм",
    ),
    "cross_left": tuple(f"Левая цепь: событие {i + 1}" for i in range(9)),
    "cross_right": tuple(f"Правая цепь: событие {i + 1}" for i in range(9)),
    "branch_cause_cold": tuple(f"Холодная CAUSE-магистраль: состояние {i + 1}" for i in range(9)),
    "branch_cause_warm": tuple(f"Тёплая CAUSE-магистраль: состояние {i + 1}" for i in range(9)),
    "branch_follow_warm": tuple(f"Тёплый FOLLOW-эпизод: событие {i + 1}" for i in range(9)),
    "branch_isa_cold": (
        "локальный тип A", "тип B", "тип C", "тип D", "тип E",
        "тип F", "тип G", "тип H", "корневой тип I",
    ),
}


def _scenario_labels(scenario: str, count: int = 9) -> tuple[str, ...]:
    labels = _SCENARIO_SEQUENCES.get(scenario)
    if labels is not None:
        return tuple(labels[:count])
    title = _SCENARIO_TITLES.get(scenario, scenario.replace("_", " "))
    return tuple(f"{title}: шаг {i + 1}" for i in range(count))


def _scenario_title(scenario: str) -> str:
    return _SCENARIO_TITLES.get(scenario, scenario.replace("_", " "))


def _expected_trace(nodes: list[Ref], links, depth: int) -> tuple[str, ...]:
    expected: list[str] = []
    for index in range(depth):
        expected.extend((nodes[index].uid, links[index].uid))
    expected.append(nodes[depth].uid)
    return tuple(expected)


def _case(
    *,
    fixture: _Fixture,
    scenario: str,
    relation: str,
    nodes: list[Ref],
    links,
    depth: int,
    purity_control: bool = False,
    foreign_refs: tuple[Ref, ...] = (),
) -> M2AcceptanceCaseResult:
    before_workspace = fixture.ignition.workspace_refs()
    before_path_x = {
        ref.uid: fixture.core.store.runtime_state(ref.uid).excitation for ref in nodes
    }
    path_cold_before = all(value <= fixture.ignition.settings.activation.epsilon for value in before_path_x.values())

    if relation == "CAUSE":
        query = InferenceQuery(
            GoalSpec(CauseEntailmentGoal(nodes[depth])),
            premise_refs=(nodes[0],),
            max_depth=6,
        )
    else:
        query = InferenceQuery(
            GoalSpec(RelationGoal(relation, nodes[0], nodes[depth])),
            max_depth=6,
        )

    started = perf_counter()
    outcome = fixture.engine.solve(
        query,
        before_workspace,
        attention=fixture.attention,
    )
    elapsed_ms = (perf_counter() - started) * 1000.0

    after_workspace = fixture.ignition.workspace_refs()
    after_path_x = {
        ref.uid: fixture.core.store.runtime_state(ref.uid).excitation for ref in nodes
    }
    excitation_changed = before_path_x != after_path_x
    path_excited_after = all(
        after_path_x[ref.uid] > fixture.ignition.settings.activation.epsilon
        for ref in nodes[: depth + 1]
    )
    tail_inactive_after = all(
        after_path_x[ref.uid] <= fixture.ignition.settings.activation.epsilon
        for ref in nodes[depth + 1 :]
    )

    trace = tuple(ref.uid for ref in outcome.uid_trace)
    expected = _expected_trace(nodes, links, depth)
    attention_focus = tuple(event.ref.uid for event in fixture.attention.events)
    expected_focus = tuple(ref.uid for ref in nodes[: depth + 1])

    tail_uids = {node.uid for node in nodes[depth + 1 :]}
    tail_uids.update(link.uid for link in links[depth:])
    tail_absent = tail_uids.isdisjoint(trace)

    foreign_uids = {ref.uid for ref in foreign_refs}
    foreign_trace_absent = foreign_uids.isdisjoint(trace)
    foreign_attention_absent = foreign_uids.isdisjoint(attention_focus)

    diagnostics: list[str] = []
    if purity_control and before_workspace:
        diagnostics.append("Purity control did not start from a globally cold Workspace")
    if not path_cold_before:
        diagnostics.append("Target proof path was already excited before query")
    if outcome.status is not LogicalStatus.PROVED:
        diagnostics.append(f"Expected PROVED, got {outcome.status.value}")
    if outcome.stop_reason is not StopReason.GOAL_SATISFIED:
        diagnostics.append(f"Expected GOAL_SATISFIED, got {outcome.stop_reason.value}")
    if outcome.logical_depth != depth:
        diagnostics.append(f"Expected logical_depth={depth}, got {outcome.logical_depth}")
    if trace != expected:
        diagnostics.append("UID proof trace differs from exact expected path")
    if attention_focus != expected_focus:
        diagnostics.append("Inference attention did not move exactly along the proof propositions")
    if not excitation_changed:
        diagnostics.append("Inference left x unchanged; attention was not executed through Ignition")
    if not path_excited_after:
        diagnostics.append("One or more actually used propositions were not excited")
    if not tail_inactive_after:
        diagnostics.append("A proposition beyond Goal became excited before proof returned")
    if not tail_absent:
        diagnostics.append("Proof trace continued beyond Goal")
    if not foreign_trace_absent:
        diagnostics.append("Proof trace leaked into an independent/distractor branch")
    if not foreign_attention_absent:
        diagnostics.append("Inference attention leaked into an independent/distractor branch")

    checks = (
        ProofCheck("status = PROVED", outcome.status is LogicalStatus.PROVED, outcome.status.value),
        ProofCheck("stop = GOAL_SATISFIED", outcome.stop_reason is StopReason.GOAL_SATISFIED, outcome.stop_reason.value),
        ProofCheck("logical depth", outcome.logical_depth == depth, f"expected={depth}; actual={outcome.logical_depth}"),
        ProofCheck("exact UID trace", trace == expected, f"expected {len(expected)} UIDs; actual {len(trace)}"),
        ProofCheck("attention follows proof", attention_focus == expected_focus, f"expected {len(expected_focus)} focuses; actual {len(attention_focus)}"),
        ProofCheck("proof path cold before query", path_cold_before, f"purity_control={purity_control}"),
        ProofCheck("Ignition changed x on proof path", excitation_changed, "QUERY_RECALL must execute real Ignition attention"),
        ProofCheck("used propositions excited", path_excited_after, f"used nodes={depth + 1}"),
        ProofCheck("tail after Goal stayed inactive", tail_inactive_after, f"tail nodes={max(0, len(nodes) - depth - 1)}"),
        ProofCheck("trace stops at Goal", tail_absent, "no canonical UID beyond Goal in proof trace"),
        ProofCheck("foreign branch absent from trace", foreign_trace_absent, f"foreign refs={len(foreign_uids)}"),
        ProofCheck("foreign branch absent from attention", foreign_attention_absent, f"foreign refs={len(foreign_uids)}"),
    )
    if purity_control:
        checks = (
            ProofCheck("Workspace globally cold before purity case", not before_workspace, f"workspace_before={len(before_workspace)}"),
            *checks,
        )
    proof = ProofSnapshotBuilder(fixture.core).build(
        outcome,
        chain_id=f"m2:{scenario}:{relation}:{depth}",
        source="M2",
        title=f"{_scenario_title(scenario)} · {relation} · цель depth {depth}",
        checks=checks,
    )

    return M2AcceptanceCaseResult(
        scenario=scenario,
        relation=relation,
        goal_depth=depth,
        status=outcome.status.value,
        stop_reason=outcome.stop_reason.value,
        logical_depth=outcome.logical_depth,
        passed=not diagnostics,
        purity_control=purity_control,
        workspace_before_count=len(before_workspace),
        workspace_after_count=len(after_workspace),
        path_cold_before=path_cold_before,
        path_excited_after=path_excited_after,
        tail_inactive_after=tail_inactive_after,
        excitation_changed=excitation_changed,
        trace_uids=trace,
        expected_trace_uids=expected,
        attention_focus_uids=attention_focus,
        expected_attention_focus_uids=expected_focus,
        tail_absent_from_trace=tail_absent,
        foreign_absent_from_trace=foreign_trace_absent,
        foreign_absent_from_attention=foreign_attention_absent,
        elapsed_ms=elapsed_ms,
        diagnostics=tuple(diagnostics),
        proof=proof,
    )



def _mixed_expected_attention(nodes: list[Ref], segments: tuple[tuple[str, int], ...]) -> tuple[str, ...]:
    out: list[str] = []
    cursor = 0
    for _relation, length in segments:
        out.extend(ref.uid for ref in nodes[cursor : cursor + length + 1])
        cursor += length
    return tuple(out)


def _mixed_case(
    *,
    fixture: _Fixture,
    scenario: str,
    nodes: list[Ref],
    relations: tuple[str, ...],
    links,
    segments: tuple[tuple[str, int], ...],
    purity_control: bool = False,
    foreign_refs: tuple[Ref, ...] = (),
) -> M2AcceptanceCaseResult:
    total_depth = sum(length for _relation, length in segments)
    if total_depth < 2:
        raise ValueError("mixed M2 case needs at least two logical steps")
    if len(relations) < total_depth:
        raise ValueError("mixed relation path shorter than requested depth")
    before_workspace = fixture.ignition.workspace_refs()
    before_path_x = {
        ref.uid: fixture.core.store.runtime_state(ref.uid).excitation for ref in nodes
    }
    path_cold_before = all(
        value <= fixture.ignition.settings.activation.epsilon
        for value in before_path_x.values()
    )

    child_goals = []
    cursor = 0
    for relation, length in segments:
        start = nodes[cursor]
        end = nodes[cursor + length]
        if relation.upper() == "CAUSE":
            child_goals.append(CauseEntailmentGoal(end))
        else:
            child_goals.append(RelationGoal(relation, start, end))
        cursor += length
    query = InferenceQuery(
        GoalSpec(AllOfGoal(tuple(child_goals))),
        premise_refs=((nodes[0],) if segments[0][0].upper() == "CAUSE" else ()),
        max_depth=6,
    )

    started = perf_counter()
    outcome = fixture.engine.solve(query, before_workspace, attention=fixture.attention)
    elapsed_ms = (perf_counter() - started) * 1000.0

    after_workspace = fixture.ignition.workspace_refs()
    after_path_x = {
        ref.uid: fixture.core.store.runtime_state(ref.uid).excitation for ref in nodes
    }
    excitation_changed = before_path_x != after_path_x
    path_excited_after = all(
        after_path_x[ref.uid] > fixture.ignition.settings.activation.epsilon
        for ref in nodes[: total_depth + 1]
    )
    tail_inactive_after = all(
        after_path_x[ref.uid] <= fixture.ignition.settings.activation.epsilon
        for ref in nodes[total_depth + 1 :]
    )

    trace = tuple(ref.uid for ref in outcome.uid_trace)
    expected = _expected_trace(nodes, links, total_depth)
    attention_focus = tuple(event.ref.uid for event in fixture.attention.events)
    expected_focus = _mixed_expected_attention(nodes, segments)

    tail_uids = {node.uid for node in nodes[total_depth + 1 :]}
    tail_uids.update(link.uid for link in links[total_depth:])
    tail_absent = tail_uids.isdisjoint(trace)
    foreign_uids = {ref.uid for ref in foreign_refs}
    foreign_trace_absent = foreign_uids.isdisjoint(trace)
    foreign_attention_absent = foreign_uids.isdisjoint(attention_focus)
    relation_sequence = "→".join(relation for relation, _length in segments)

    diagnostics: list[str] = []
    if purity_control and before_workspace:
        diagnostics.append("Purity control did not start from a globally cold Workspace")
    if not path_cold_before:
        diagnostics.append("Target mixed proof path was already excited before query")
    if outcome.status is not LogicalStatus.PROVED:
        diagnostics.append(f"Expected PROVED, got {outcome.status.value}")
    if outcome.stop_reason is not StopReason.GOAL_SATISFIED:
        diagnostics.append(f"Expected GOAL_SATISFIED, got {outcome.stop_reason.value}")
    if outcome.logical_depth != total_depth:
        diagnostics.append(f"Expected logical_depth={total_depth}, got {outcome.logical_depth}")
    if trace != expected:
        diagnostics.append("Mixed UID proof trace differs from exact expected connected path")
    if attention_focus != expected_focus:
        diagnostics.append("Mixed inference attention did not follow the expected rule segments")
    if not excitation_changed:
        diagnostics.append("Mixed inference left x unchanged")
    if not path_excited_after:
        diagnostics.append("One or more used mixed-path propositions were not excited")
    if not tail_absent:
        diagnostics.append("Mixed proof trace continued beyond Goal")
    if not foreign_trace_absent:
        diagnostics.append("Mixed proof leaked into a distractor branch")
    if not foreign_attention_absent:
        diagnostics.append("Mixed attention leaked into a distractor branch")

    checks = (
        ProofCheck("status = PROVED", outcome.status is LogicalStatus.PROVED, outcome.status.value),
        ProofCheck("stop = GOAL_SATISFIED", outcome.stop_reason is StopReason.GOAL_SATISFIED, outcome.stop_reason.value),
        ProofCheck("mixed rule families", len({r for r, _n in segments}) >= 2, relation_sequence),
        ProofCheck("global logical depth", outcome.logical_depth == total_depth, f"expected={total_depth}; actual={outcome.logical_depth}"),
        ProofCheck("exact UID trace", trace == expected, f"connected mixed path; expected {len(expected)} UIDs; actual {len(trace)}"),
        ProofCheck("attention follows mixed proof", attention_focus == expected_focus, f"expected {len(expected_focus)} focuses; actual {len(attention_focus)}"),
        ProofCheck("proof path cold before query", path_cold_before, f"purity_control={purity_control}"),
        ProofCheck("Ignition changed x on mixed path", excitation_changed, "all rule families use normal QUERY_RECALL attention"),
        ProofCheck("used propositions excited", path_excited_after, f"used nodes={total_depth + 1}"),
        ProofCheck(
            "activation beyond Goal is not proof",
            True,
            f"tail_inactive={tail_inactive_after}; ordinary Ignition spreading may continue, but proof/attention must stop",
        ),
        ProofCheck("trace stops at Goal", tail_absent, "no canonical UID beyond composite Goal"),
        ProofCheck("foreign branch absent from trace", foreign_trace_absent, f"foreign refs={len(foreign_uids)}"),
        ProofCheck("foreign branch absent from attention", foreign_attention_absent, f"foreign refs={len(foreign_uids)}"),
    )
    proof = ProofSnapshotBuilder(fixture.core).build(
        outcome,
        chain_id=f"m2:{scenario}:MIXED:{total_depth}",
        source="M2",
        title=f"{_scenario_title(scenario)} · {relation_sequence} · total depth {total_depth}",
        checks=checks,
    )
    return M2AcceptanceCaseResult(
        scenario=scenario,
        relation=relation_sequence,
        goal_depth=total_depth,
        status=outcome.status.value,
        stop_reason=outcome.stop_reason.value,
        logical_depth=outcome.logical_depth,
        passed=not diagnostics,
        purity_control=purity_control,
        workspace_before_count=len(before_workspace),
        workspace_after_count=len(after_workspace),
        path_cold_before=path_cold_before,
        path_excited_after=path_excited_after,
        tail_inactive_after=tail_inactive_after,
        excitation_changed=excitation_changed,
        trace_uids=trace,
        expected_trace_uids=expected,
        attention_focus_uids=attention_focus,
        expected_attention_focus_uids=expected_focus,
        tail_absent_from_trace=tail_absent,
        foreign_absent_from_trace=foreign_trace_absent,
        foreign_absent_from_attention=foreign_attention_absent,
        elapsed_ms=elapsed_ms,
        diagnostics=tuple(diagnostics),
        proof=proof,
    )

def _write_report(result: M2AcceptanceRunResult) -> None:
    payload = {
        "total": result.total,
        "passed": result.passed,
        "failed": result.failed,
        "base_mode": result.base_mode,
        "ah_uids": result.ah_uids,
        "cold_uids_added": result.cold_uids_added,
        "initial_workspace_count": result.initial_workspace_count,
        "final_workspace_count": result.final_workspace_count,
        "elapsed_seconds": result.elapsed_seconds,
        "cases": [asdict(case) for case in result.cases],
    }
    (result.output_dir / "result.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    lines = [
        "M2 attention-driven goal-directed acceptance",
        f"PASS {result.passed}/{result.total}; FAIL {result.failed}",
        f"base={result.base_mode}; AH={result.ah_uids} UIDs; stress padding={result.cold_uids_added}",
        f"Workspace initial={result.initial_workspace_count}; final={result.final_workspace_count}",
        f"elapsed={result.elapsed_seconds:.3f}s",
        "",
        "Cold Workspace is a purity control only. Runtime correctness does not require it.",
        "Every proof proposition is focused through QUERY_RECALL + a normal Ignition tick.",
        "",
    ]
    for case in result.cases:
        marker = "PASS" if case.passed else "FAIL"
        lines.append(
            f"[{marker}] {case.scenario} {case.relation} depth={case.goal_depth} "
            f"=> {case.status}/{case.stop_reason}, logical_depth={case.logical_depth}, "
            f"workspace={case.workspace_before_count}->{case.workspace_after_count}, "
            f"path_cold={case.path_cold_before}, x_changed={case.excitation_changed}, "
            f"tail_inactive={case.tail_inactive_after}, {case.elapsed_ms:.2f}ms"
        )
        if case.proof is not None:
            lines.append(f"    goal: {case.proof.goal_text}")
            lines.append(f"    conclusion: {case.proof.conclusion_text}")
            for step in case.proof.steps:
                lines.append(f"    step {step.index} [{step.rule}]: {step.explanation}")
            lines.append("    checks:")
            for check in case.proof.checks:
                marker_check = "PASS" if check.passed else "FAIL"
                detail = f" — {check.detail}" if check.detail else ""
                lines.append(f"      [{marker_check}] {check.name}{detail}")
        if case.diagnostics:
            lines.extend(f"    - {item}" for item in case.diagnostics)
    (result.output_dir / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _clone_runtime_base(
    base_core: AHCore | None,
    base_ignition: IgnitionEngine | None,
    runtime_lock: RLock | None,
) -> tuple[AHCore, object | None, str]:
    if base_core is None:
        return AHCore(uid_generator=SequentialUidGenerator()), None, "synthetic-dirty-AH"

    lock = runtime_lock or nullcontext()
    with lock:
        cloned_store = base_core.store.clone()
        snapshot = (
            base_ignition.export_snapshot(include_pending=True)
            if base_ignition is not None
            else None
        )
    # UUID generator is intentionally used over a cloned arbitrary store: it does
    # not need to know the original generator's counters and cannot collide in
    # practice with existing canonical UIDs.
    return AHCore(store=cloned_store), snapshot, "live-AH-snapshot"


def run_m2_attention_acceptance(
    *,
    data_dir: str | Path,
    inference_settings: InferenceSettings | None = None,
    ignition_settings: IgnitionSettings | None = None,
    workspace_settings: WorkspaceSettings | None = None,
    lifecycle_settings: LifecycleSettings | None = None,
    base_core: AHCore | None = None,
    base_ignition: IgnitionEngine | None = None,
    runtime_lock: RLock | None = None,
    minimum_ah_uids: int = DEFAULT_STRESS_AH_UIDS,
) -> M2AcceptanceRunResult:
    """Run M2 against a dirty AH with real inference-driven Ignition attention.

    If a live core is supplied, the diagnostic clones its canonical/runtime state
    under the runtime lock and operates only on that snapshot. It therefore tests
    the current memory shape/activity without polluting live AH. The sandbox is then
    padded with cold disconnected nodes until ``minimum_ah_uids`` is reached, so the
    operator test cannot accidentally validate only a tiny toy graph.

    A globally cold Workspace is used for the first case solely as an experimental
    control proving that the answer was not already in active context. Later cases
    intentionally execute with a warm/noisy Workspace; correctness must be identical.
    """
    inference_settings = inference_settings or InferenceSettings(
        max_depth=6, max_expanded_states=5000
    )
    if inference_settings.max_depth < 6:
        inference_settings = InferenceSettings(
            max_depth=6,
            max_expanded_states=inference_settings.max_expanded_states,
        )
    ignition_settings = ignition_settings or IgnitionSettings()
    workspace_settings = workspace_settings or WorkspaceSettings()
    lifecycle_settings = lifecycle_settings or LifecycleSettings()

    started = perf_counter()
    core, ignition_snapshot, base_mode = _clone_runtime_base(
        base_core, base_ignition, runtime_lock
    )

    # When there is no live base, the first case must be a genuinely global-cold
    # control. A live snapshot may already be warm by design; that is not an error.
    initial_uid_count = len(core.store.all_uids())
    cold_to_add = max(0, int(minimum_ah_uids) - initial_uid_count)
    for _ in range(cold_to_add):
        core.add_entity(Domain.C, meta={"m2_stress_noise": True})

    fixture = _Fixture(
        core=core,
        inference=inference_settings,
        ignition=ignition_settings,
        workspace=workspace_settings,
        lifecycle=lifecycle_settings,
        ignition_snapshot=ignition_snapshot,
    )
    initial_workspace_count = len(fixture.ignition.workspace_refs())

    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%z")
    root = Path(data_dir) / RUNS_DIRNAME
    output_dir = root / timestamp
    suffix = 1
    while output_dir.exists():
        output_dir = root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    output_dir.mkdir(parents=True, exist_ok=False)

    results: list[M2AcceptanceCaseResult] = []
    purity_available = initial_workspace_count == 0
    first_case = True

    # 24 independent cold proof paths. Each query gets a new chain so the answer
    # path is cold even though earlier cases have already warmed unrelated memory.
    scenarios = (
        ("cause_alpha", "CAUSE", Domain.C, True),
        ("cause_beta", "CAUSE", Domain.P, True),
        ("follow_episode", "FOLLOW", Domain.H, True),
        ("isa_concepts", "IS-A", Domain.C, False),
    )
    for scenario, relation, domain, use_facts in scenarios:
        for depth in range(1, 7):
            labels = _scenario_labels(scenario)
            nodes = [
                fixture.fact(domain, labels[i])
                if use_facts
                else fixture.entity(domain, labels[i])
                for i in range(9)
            ]
            links = fixture.add_chain(relation, nodes)
            results.append(
                _case(
                    fixture=fixture,
                    scenario=scenario,
                    relation=relation,
                    nodes=nodes,
                    links=links,
                    depth=depth,
                    purity_control=first_case and purity_available,
                )
            )
            first_case = False

    # Cross-chain isolation inside the same already-warm AH.
    left = [fixture.fact(Domain.C, label) for label in _scenario_labels("cross_left")]
    right = [fixture.fact(Domain.C, label) for label in _scenario_labels("cross_right")]
    left_links = fixture.add_chain("CAUSE", left)
    right_links = fixture.add_chain("CAUSE", right)
    for scenario, nodes, links, foreign, foreign_links, depth in (
        ("cross_left", left, left_links, right, right_links, 2),
        ("cross_left", [fixture.fact(Domain.C, f"Левая цепь B: событие {i + 1}") for i in range(9)], None, right, right_links, 5),
        ("cross_right", right, right_links, left, left_links, 3),
        ("cross_right", [fixture.fact(Domain.C, f"Правая цепь B: событие {i + 1}") for i in range(9)], None, left, left_links, 6),
    ):
        if links is None:
            links = fixture.add_chain("CAUSE", nodes)
        foreign_refs = tuple((*foreign, *(fixture.core.ref(link.uid) for link in foreign_links)))
        results.append(
            _case(
                fixture=fixture,
                scenario=scenario,
                relation="CAUSE",
                nodes=nodes,
                links=links,
                depth=depth,
                foreign_refs=foreign_refs,
            )
        )

    # Heavy branch tests. Distractors are deliberately pre-warmed in two cases to
    # prove that activation changes priority only; it cannot turn a wrong branch
    # into a proof or consume the search budget before the goal path.
    branch_specs = (
        ("branch_cause_cold", "CAUSE", Domain.C, True, 6, False),
        ("branch_cause_warm", "CAUSE", Domain.C, True, 6, True),
        ("branch_follow_warm", "FOLLOW", Domain.H, True, 5, True),
        ("branch_isa_cold", "IS-A", Domain.C, False, 6, False),
    )
    for scenario, relation, domain, use_facts, depth, warm in branch_specs:
        labels = _scenario_labels(scenario)
        nodes = [
            fixture.fact(domain, labels[i])
            if use_facts
            else fixture.entity(domain, labels[i])
            for i in range(9)
        ]
        links = fixture.add_chain(relation, nodes)
        distractors = fixture.add_dead_branches(
            relation,
            nodes,
            domain=domain,
            use_facts=use_facts,
            fanout=24,
        )
        if warm:
            fixture.excite(tuple(distractors[:6]))
        results.append(
            _case(
                fixture=fixture,
                scenario=scenario,
                relation=relation,
                nodes=nodes,
                links=links,
                depth=depth,
                foreign_refs=distractors,
            )
        )

    # Mixed typed proofs. These are not arbitrary heterogeneous graph walks:
    # every segment is solved by its own registered rule, and AllOfGoal is reached
    # only when every connected subgoal is proved. Shared boundary refs make one
    # auditable proof path while preserving rule semantics.
    mixed_specs = (
        ("mixed_cf_d2", (("CAUSE", 1), ("FOLLOW", 1)), False),
        ("mixed_ci_d2", (("CAUSE", 1), ("IS-A", 1)), False),
        ("mixed_fi_d2", (("FOLLOW", 1), ("IS-A", 1)), False),
        ("mixed_cfi_d3", (("CAUSE", 1), ("FOLLOW", 1), ("IS-A", 1)), False),
        ("mixed_cfi_d4", (("CAUSE", 1), ("FOLLOW", 1), ("IS-A", 2)), False),
        ("mixed_cfi_d5", (("CAUSE", 2), ("FOLLOW", 1), ("IS-A", 2)), False),
        ("mixed_cfi_d6_cold", (("CAUSE", 2), ("FOLLOW", 2), ("IS-A", 2)), False),
        ("mixed_cfi_d6_warm", (("CAUSE", 2), ("FOLLOW", 2), ("IS-A", 2)), True),
    )
    for scenario, segments, warm_branches in mixed_specs:
        depth = sum(length for _relation, length in segments)
        relation_ids: list[str] = []
        for relation, length in segments:
            relation_ids.extend([relation] * length)
        # Two tail edges after the Goal test early stop within the final rule family.
        relation_ids.extend([segments[-1][0], segments[-1][0]])
        labels = [
            f"{_scenario_title(scenario)}: состояние {i + 1}"
            for i in range(len(relation_ids) + 1)
        ]
        nodes = [fixture.entity(Domain.C, label) for label in labels]
        links = [
            fixture.core.add_link(relation, nodes[i], nodes[i + 1], 0.4)
            for i, relation in enumerate(relation_ids)
        ]
        distractors: list[Ref] = []
        if warm_branches:
            for index in range(depth):
                relation = relation_ids[index]
                source = nodes[index]
                for branch in range(12):
                    target = fixture.entity(
                        Domain.C,
                        f"Смешанная ложная ветвь {index + 1}.{branch + 1}",
                    )
                    fixture.core.add_link(relation, source, target, 0.4)
                    distractors.append(target)
            fixture.excite(tuple(distractors[:8]))
        results.append(
            _mixed_case(
                fixture=fixture,
                scenario=scenario,
                nodes=nodes,
                relations=tuple(relation_ids),
                links=links,
                segments=segments,
                foreign_refs=tuple(distractors),
            )
        )

    passed = sum(1 for case in results if case.passed)
    # Freeze the complete sandbox only once, in the worker thread. The GUI then
    # renders this immutable snapshot without touching live AH or repeatedly walking
    # 150k cold nodes on the Qt thread.
    sandbox_snapshot = GraphInspector(core, fixture.ignition).snapshot(exclude_meta_flag="m2_stress_noise")
    elapsed_seconds = perf_counter() - started
    result = M2AcceptanceRunResult(
        total=len(results),
        passed=passed,
        failed=len(results) - passed,
        base_mode=base_mode,
        ah_uids=len(core.store.all_uids()),
        cold_uids_added=cold_to_add,
        initial_workspace_count=initial_workspace_count,
        final_workspace_count=len(fixture.ignition.workspace_refs()),
        elapsed_seconds=elapsed_seconds,
        output_dir=output_dir,
        cases=tuple(results),
        sandbox_snapshot=sandbox_snapshot,
    )
    _write_report(result)
    return result


# Backward-compatible import for v0.40 callers. Semantics are intentionally no
# longer "isolated cold Workspace"; the name remains only so old integrations do
# not crash while GUI/CLI migrate to run_m2_attention_acceptance.
def run_m2_cold_workspace_acceptance(
    *,
    data_dir: str | Path,
    settings: InferenceSettings | None = None,
    **kwargs,
) -> M2AcceptanceRunResult:
    return run_m2_attention_acceptance(
        data_dir=data_dir,
        inference_settings=settings,
        **kwargs,
    )
