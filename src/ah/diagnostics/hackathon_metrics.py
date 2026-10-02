from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
import gc
import json
import re
from typing import Any, Iterable, Mapping, Sequence

from ah.config import AppConfig, PacemakerSettings
from ah.core import AHCore, SequentialUidGenerator
from ah.dsl import DSLInterpreter
from ah.ignition import IgnitionEngine
from ah.integration.contracts import SeedReason
from ah.model import ActantRole, Domain, Property


_MANDATORY_M1_ROLES = (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.LOCATION)
_ROLE_WEIGHTS = {
    ActantRole.SUBJECT: 2.0,
    ActantRole.OBJECT: 2.0,
}


@dataclass(frozen=True, slots=True)
class RoleMetric:
    role: str
    gold: int
    predicted: int
    correct: int
    precision: float
    recall: float
    f1: float
    weight: float
    evaluated: bool = True


@dataclass(frozen=True, slots=True)
class M1Report:
    roles: tuple[RoleMetric, ...]
    weighted_sum_as_stated: float
    weighted_mean: float
    mandatory_roles_present: bool
    source: str | None = None


@dataclass(frozen=True, slots=True)
class M2QuestionObservation:
    correct: bool
    depth: int
    trace_complete: bool
    label: str = ""


@dataclass(frozen=True, slots=True)
class M2ScoreReport:
    question_count: int
    d_max: int
    explain_score: float
    contributions: tuple[float, ...]
    all_correct: bool
    all_traces_complete: bool


@dataclass(frozen=True, slots=True)
class M3Report:
    orphan_nodes_before: int
    orphan_nodes_after: int
    live_nodes_before: int
    live_nodes_after: int
    ticks_budget: int
    ticks_until_orphans_gone: int | None
    gc_efficiency: float
    live_preservation: float
    passed: bool
    elapsed_ms: float
    output_dir: str | None = None
    pacemaker_enabled: bool = False
    live_missing: tuple[str, ...] = ()
    remaining_orphans: tuple[str, ...] = ()


M3_RUNS_DIRNAME = "m3_runs"




@dataclass(frozen=True, slots=True)
class TickBenchmarkReport:
    graph_units_n_plus_l: int
    canonical_uids: int
    measured_ticks: int
    warmup_ticks: int
    mean_ms: float
    max_ms: float
    p95_ms: float
    passes_500ms: bool

@dataclass(frozen=True, slots=True)
class M4Report:
    ah_explainability: float
    rag_explainability: float
    ah_hallucination: float
    rag_hallucination: float
    delta_explainability: float
    delta_hallucination: float


@dataclass(frozen=True, slots=True)
class M5Report:
    ah_slm_f1: float
    rag_slm_f1: float
    ah_llm_f1: float
    rag_llm_f1: float
    robustness_gain: float


def _norm(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    return re.sub(r"\s+", " ", text)


def _predicate_name(item: Mapping[str, Any]) -> str:
    predicate = item.get("predicate")
    if not isinstance(predicate, Mapping):
        return ""
    return _norm(predicate.get("normalized_hint") or predicate.get("surface"))


def _gold_role_items(oracle_payload: Mapping[str, Any]) -> list[tuple[int, str, str, str]]:
    out: list[tuple[int, str, str, str]] = []
    cases = oracle_payload.get("cases")
    if not isinstance(cases, list):
        raise ValueError("oracle payload must contain cases[]")
    for case_index, case in enumerate(cases, start=1):
        if not isinstance(case, Mapping):
            continue
        expectation = case.get("expect")
        if not isinstance(expectation, Mapping):
            continue
        perception = expectation.get("perception")
        if not isinstance(perception, Mapping):
            continue
        assertions = perception.get("assertions")
        if not isinstance(assertions, list):
            continue
        for assertion in assertions:
            if not isinstance(assertion, Mapping):
                continue
            predicate = _norm(assertion.get("predicate"))
            roles = assertion.get("roles")
            if not isinstance(roles, Mapping):
                continue
            for role, value in roles.items():
                value_norm = _norm(value)
                if value_norm:
                    out.append((case_index, predicate, str(role).upper(), value_norm))
    return out


def _predicted_role_items(turn_records: Sequence[Mapping[str, Any]]) -> list[tuple[int, str, str, str]]:
    out: list[tuple[int, str, str, str]] = []
    for record in turn_records:
        try:
            case_index = int(record.get("index"))
        except (TypeError, ValueError):
            continue
        perception = record.get("perception_result")
        if not isinstance(perception, Mapping):
            continue
        assertions = perception.get("assertions")
        if not isinstance(assertions, list):
            continue
        for assertion in assertions:
            if not isinstance(assertion, Mapping):
                continue
            predicate = _predicate_name(assertion)
            actants = assertion.get("actants")
            if not isinstance(actants, list):
                continue
            for actant in actants:
                if not isinstance(actant, Mapping):
                    continue
                role = str(actant.get("role") or "").upper()
                value = _norm(actant.get("normalized_hint") or actant.get("mention"))
                if role and value:
                    out.append((case_index, predicate, role, value))
    return out


def score_m1_role_f1(
    gold_items: Iterable[tuple[int, str, str, str]],
    predicted_items: Iterable[tuple[int, str, str, str]],
    *,
    source: str | None = None,
) -> M1Report:
    """Score actant extraction without using LLM answer generation.

    Items are ``(case_index, predicate, role, normalized_value)``.  Matching is a
    multiset intersection, so duplicate frames do not create free true positives.

    The hackathon statement prints ``Σ(w_r * F1_r)`` while also using a 0.6
    acceptance threshold.  To avoid silently changing that source formula, the
    report exposes both the literal weighted sum and the normalized weighted mean.
    The latter is the bounded [0,1] value suitable for the stated threshold.
    """
    gold = Counter((int(i), _norm(p), str(r).upper(), _norm(v)) for i, p, r, v in gold_items)
    pred = Counter((int(i), _norm(p), str(r).upper(), _norm(v)) for i, p, r, v in predicted_items)

    roles = {key[2] for key in gold} | {key[2] for key in pred}
    roles.update(role.value for role in _MANDATORY_M1_ROLES)
    rows: list[RoleMetric] = []
    weighted_sum = 0.0
    weight_total = 0.0
    mandatory_present = True

    for role_name in sorted(roles):
        gold_count = sum(count for key, count in gold.items() if key[2] == role_name)
        pred_count = sum(count for key, count in pred.items() if key[2] == role_name)
        correct = sum(
            min(count, pred.get(key, 0))
            for key, count in gold.items()
            if key[2] == role_name
        )
        precision = correct / pred_count if pred_count else (1.0 if gold_count == 0 else 0.0)
        recall = correct / gold_count if gold_count else (1.0 if pred_count == 0 else 0.0)
        f1 = (2.0 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        evaluated = (gold_count + pred_count) > 0
        try:
            role_enum = ActantRole(role_name)
        except ValueError:
            weight = 1.0
        else:
            weight = _ROLE_WEIGHTS.get(role_enum, 1.0)
        if evaluated:
            weighted_sum += weight * f1
            weight_total += weight
        if role_name in {role.value for role in _MANDATORY_M1_ROLES} and gold_count == 0:
            mandatory_present = False
        rows.append(
            RoleMetric(
                role=role_name,
                gold=gold_count,
                predicted=pred_count,
                correct=correct,
                precision=precision,
                recall=recall,
                f1=f1,
                weight=weight,
                evaluated=evaluated,
            )
        )

    weighted_mean = weighted_sum / weight_total if weight_total else 0.0
    return M1Report(
        roles=tuple(rows),
        weighted_sum_as_stated=weighted_sum,
        weighted_mean=weighted_mean,
        mandatory_roles_present=mandatory_present,
        source=source,
    )


def score_m1_acceptance_bundle(run_dir: str | Path) -> M1Report:
    root = Path(run_dir)
    oracle_path = root / "oracle_used.json"
    if not oracle_path.is_file():
        raise FileNotFoundError(f"acceptance oracle not found: {oracle_path}")
    oracle = json.loads(oracle_path.read_text(encoding="utf-8-sig"))
    records: list[Mapping[str, Any]] = []
    for path in sorted(root.glob("turn_*.json")):
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(payload, Mapping):
            records.append(payload)
    if not records:
        raise ValueError(f"no turn_*.json records found in {root}")
    return score_m1_role_f1(
        _gold_role_items(oracle),
        _predicted_role_items(records),
        source=str(root.resolve()),
    )


def score_m2_explainability(
    observations: Sequence[M2QuestionObservation],
    *,
    d_max: int = 6,
    expected_count: int | None = 20,
) -> M2ScoreReport:
    if d_max <= 0:
        raise ValueError("d_max must be > 0")
    if expected_count is not None and len(observations) != expected_count:
        raise ValueError(f"M2 requires exactly {expected_count} questions, got {len(observations)}")
    if not observations:
        raise ValueError("M2 observations must be non-empty")
    contributions: list[float] = []
    for item in observations:
        if item.depth < 1 or item.depth > d_max:
            raise ValueError(f"M2 depth must be in [1,{d_max}], got {item.depth}")
        contributions.append(
            (1.0 if item.correct else 0.0)
            * (float(item.depth) / float(d_max))
            * (1.0 if item.trace_complete else 0.0)
        )
    return M2ScoreReport(
        question_count=len(observations),
        d_max=d_max,
        explain_score=sum(contributions) / len(observations),
        contributions=tuple(contributions),
        all_correct=all(item.correct for item in observations),
        all_traces_complete=all(item.trace_complete for item in observations),
    )


def score_m4_comparison(
    *,
    ah_explainability: float,
    rag_explainability: float,
    ah_hallucination: float,
    rag_hallucination: float,
) -> M4Report:
    for name, value in (
        ("ah_explainability", ah_explainability),
        ("rag_explainability", rag_explainability),
        ("ah_hallucination", ah_hallucination),
        ("rag_hallucination", rag_hallucination),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0,1]")
    return M4Report(
        ah_explainability=ah_explainability,
        rag_explainability=rag_explainability,
        ah_hallucination=ah_hallucination,
        rag_hallucination=rag_hallucination,
        delta_explainability=ah_explainability - rag_explainability,
        delta_hallucination=rag_hallucination - ah_hallucination,
    )


def score_m5_robustness(
    *,
    ah_slm_f1: float,
    rag_slm_f1: float,
    ah_llm_f1: float,
    rag_llm_f1: float,
) -> M5Report:
    for name, value in (
        ("ah_slm_f1", ah_slm_f1),
        ("rag_slm_f1", rag_slm_f1),
        ("ah_llm_f1", ah_llm_f1),
        ("rag_llm_f1", rag_llm_f1),
    ):
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be in [0,1]")
    if rag_slm_f1 <= 0.0 or rag_llm_f1 <= 0.0:
        raise ValueError("M5 VanillaRAG F1 denominators must be > 0")
    gain = (ah_slm_f1 / rag_slm_f1) - (ah_llm_f1 / rag_llm_f1)
    return M5Report(ah_slm_f1, rag_slm_f1, ah_llm_f1, rag_llm_f1, gain)


def _m3_uid_debug(core: AHCore, engine: IgnitionEngine, uid: str) -> dict[str, Any]:
    if not core.store.has_uid(uid):
        return {"uid": uid, "exists": False}
    kind = core.store.kind_of(uid)
    excitation = 0.0
    try:
        excitation = float(core.store.runtime_state(uid).excitation)
    except KeyError:
        pass
    threshold = float(engine.workspace_settings.threshold)
    return {
        "uid": uid,
        "exists": True,
        "kind": getattr(kind, "value", str(kind)),
        "excitation": excitation,
        "pacemaker_only": uid in engine._pacemaker_only_excitation,
        "in_workspace": excitation > threshold,
        "lifetime_managed": core.store.is_lifetime_managed(uid),
        "birth_tick": core.store.lifetime_birth_tick(uid),
    }


def _write_m3_bundle(
    data_dir: Path,
    *,
    report: M3Report,
    config: AppConfig,
    orphan_records: list[dict[str, Any]],
    live_records: dict[str, Any],
    tick_records: list[dict[str, Any]],
    remaining: list[dict[str, Any]],
) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%z")
    root = Path(data_dir) / M3_RUNS_DIRNAME
    output_dir = root / timestamp
    suffix = 1
    while output_dir.exists():
        output_dir = root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "summary.json").write_text(
        json.dumps(asdict(report) | {"output_dir": str(output_dir)}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    lines = [
        f"M3 {'PASS' if report.passed else 'FAIL'}",
        f"orphans {report.orphan_nodes_before} -> {report.orphan_nodes_after}",
        f"live {report.live_nodes_before} -> {report.live_nodes_after}",
        f"GC_efficiency={report.gc_efficiency}",
        f"live_preservation={report.live_preservation}",
        f"ticks_until_orphans_gone={report.ticks_until_orphans_gone}",
        f"ticks_budget={report.ticks_budget}",
        f"pacemaker_enabled={report.pacemaker_enabled}",
        f"elapsed_ms={report.elapsed_ms:.2f}",
    ]
    if report.live_missing:
        lines.append(f"live_missing={','.join(report.live_missing)}")
    if report.remaining_orphans:
        lines.append(f"remaining_orphans={','.join(report.remaining_orphans)}")
    (output_dir / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "config_snapshot.json").write_text(
        json.dumps(
            {
                "initial_lifetime_ticks": config.lifecycle.initial_lifetime_ticks,
                "gc_enabled": config.lifecycle.gc_enabled,
                "orphan_cleanup": config.lifecycle.orphan_cleanup,
                "workspace_threshold": config.workspace.threshold,
                "nu": config.ignition.nu,
                "tick_interval_seconds": config.ignition.tick_interval_seconds,
                "pacemaker": {
                    "enabled": config.ignition.pacemaker.enabled,
                    "target_policy": config.ignition.pacemaker.target_policy,
                    "include_symbols": config.ignition.pacemaker.include_symbols,
                    "domains": list(config.ignition.pacemaker.domains),
                },
                "decay_alpha": config.ignition.decay.alpha,
                "pacemaker_pulse": config.ignition.seeds.pacemaker,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (output_dir / "orphans.json").write_text(
        json.dumps(orphan_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "live.json").write_text(
        json.dumps(live_records, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    with (output_dir / "ticks.jsonl").open("w", encoding="utf-8") as fh:
        for row in tick_records:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    (output_dir / "remaining_after.json").write_text(
        json.dumps(remaining, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return output_dir


def run_m3_gc_acceptance(
    config: AppConfig,
    *,
    orphan_count: int = 200,
    live_fact_count: int = 100,
    ticks_budget: int = 50,
    data_dir: Path | str | None = None,
) -> M3Report:
    """Committee-shape local M3 harness.

    Ignition starts first with the configured pacemaker. Live structure and the
    200 isolated nodes are then created through the public DSL, the same surface
    the committee can use. Ordinary ticks include ν.
    """
    if orphan_count <= 0 or live_fact_count <= 0 or ticks_budget <= 0:
        raise ValueError("M3 counts and ticks_budget must be > 0")

    core = AHCore(uid_generator=SequentialUidGenerator())
    engine = IgnitionEngine(core, config.ignition, config.workspace, config.lifecycle)
    dsl = DSLInterpreter(core)

    predicate = dsl.execute('addAbstractSymbol forms="live"').value
    template = dsl.execute(
        f'addElement domain=C kind=T predicate=@{predicate.uid} roles=SUBJECT'
    ).value
    live_uids: set[str] = {predicate.uid, template.uid}
    for index in range(live_fact_count):
        entity = dsl.execute(f'addElement domain=C kind=M name="live-{index}"').value
        node = dsl.execute(
            f'addElement domain=C kind=N template=@{template.uid} SUBJECT=@{entity.uid} weight=0.4'
        ).value
        live_uids.update((entity.uid, node.uid))

    orphan_uids: list[str] = []
    for index in range(orphan_count):
        entity = dsl.execute(
            f'addElement domain=C kind=M name="committee-orphan-{index}"'
        ).value
        orphan_uids.append(entity.uid)
    orphan_set = set(orphan_uids)

    live_before = sum(core.store.has_uid(uid) for uid in live_uids)
    orphan_before = sum(core.store.has_uid(uid) for uid in orphan_uids)
    gone_at: int | None = None
    tick_records: list[dict[str, Any]] = []
    orphan_gone: dict[str, int] = {}
    started = perf_counter()
    previous_live = set(uid for uid in live_uids if core.store.has_uid(uid))
    for tick in range(1, ticks_budget + 1):
        result = engine.tick()
        live_now = {uid for uid in live_uids if core.store.has_uid(uid)}
        live_missing_now = sorted(previous_live - live_now)
        previous_live = live_now
        remaining_now = [uid for uid in orphan_uids if core.store.has_uid(uid)]
        for uid in orphan_uids:
            if uid not in orphan_gone and not core.store.has_uid(uid):
                orphan_gone[uid] = tick
        gc = result.gc
        tick_records.append(
            {
                "tick": result.tick,
                "loop": tick,
                "deleted": list(gc.deleted) if gc is not None else [],
                "orphan_deleted": list(gc.orphan_deleted) if gc is not None else [],
                "protected": list(gc.protected) if gc is not None else [],
                "reasons": dict(gc.reasons) if gc is not None else {},
                "orphans_remaining": len(remaining_now),
                "pacemaker_targets": [
                    uid for uid in result.pacemaker_targets if uid in orphan_set
                ],
                "live_missing": live_missing_now,
            }
        )
        if gone_at is None and not remaining_now:
            gone_at = tick
    elapsed_ms = (perf_counter() - started) * 1000.0

    orphan_after = sum(core.store.has_uid(uid) for uid in orphan_uids)
    live_after = sum(core.store.has_uid(uid) for uid in live_uids)
    live_missing = tuple(sorted(uid for uid in live_uids if not core.store.has_uid(uid)))
    remaining_orphans = tuple(uid for uid in orphan_uids if core.store.has_uid(uid))
    efficiency = 1.0 - (orphan_after / orphan_before) if orphan_before else 1.0
    live_preservation = live_after / live_before if live_before else 1.0
    report = M3Report(
        orphan_nodes_before=orphan_before,
        orphan_nodes_after=orphan_after,
        live_nodes_before=live_before,
        live_nodes_after=live_after,
        ticks_budget=ticks_budget,
        ticks_until_orphans_gone=gone_at,
        gc_efficiency=efficiency,
        live_preservation=live_preservation,
        passed=(
            orphan_before == orphan_count
            and orphan_after == 0
            and live_after == live_before
            and gone_at is not None
            and gone_at <= ticks_budget
        ),
        elapsed_ms=elapsed_ms,
        pacemaker_enabled=bool(config.ignition.pacemaker.enabled),
        live_missing=live_missing,
        remaining_orphans=remaining_orphans,
    )
    output_dir: Path | None = None
    if data_dir is not None:
        remaining_debug = [_m3_uid_debug(core, engine, uid) for uid in remaining_orphans]
        orphan_records = [
            {
                "uid": uid,
                "birth_tick": core.store.lifetime_birth_tick(uid) if core.store.has_uid(uid) else None,
                "gone_at": orphan_gone.get(uid),
                "still_present": core.store.has_uid(uid),
            }
            for uid in orphan_uids
        ]
        live_records = {
            "before": live_before,
            "after": live_after,
            "missing": list(live_missing),
            "uids": sorted(live_uids),
        }
        output_dir = _write_m3_bundle(
            Path(data_dir),
            report=report,
            config=config,
            orphan_records=orphan_records,
            live_records=live_records,
            tick_records=tick_records,
            remaining=remaining_debug,
        )
        report = replace(report, output_dir=str(output_dir))
    return report


def write_metric_report(path: str | Path, report: Any) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = asdict(report) if hasattr(report, "__dataclass_fields__") else report
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return target


def run_tick_benchmark(
    config: AppConfig,
    *,
    target_graph_units: int = 1000,
    measured_ticks: int = 20,
    warmup_ticks: int = 3,
) -> TickBenchmarkReport:
    """Local reference benchmark for the hard <=500 ms/tick requirement.

    ``graph_units_n_plus_l`` follows the task wording by counting hypernodes N plus
    canonical links L.  The fixture deliberately gives one predicate many N
    instances, creating a non-trivial T→N fanout once the lexical S is seeded.
    This is a deterministic local readiness benchmark, not a substitute for the
    committee's hardware measurement.
    """
    if target_graph_units < 2 or measured_ticks <= 0 or warmup_ticks < 0:
        raise ValueError("invalid tick benchmark parameters")

    core = AHCore(uid_generator=SequentialUidGenerator())
    quiet_ignition = type(config.ignition)(
        tick_interval_seconds=config.ignition.tick_interval_seconds,
        nu=config.ignition.nu,
        x_max=config.ignition.x_max,
        activation=config.ignition.activation,
        decay=config.ignition.decay,
        plasticity=config.ignition.plasticity,
        seeds=config.ignition.seeds,
        pacemaker=PacemakerSettings(enabled=False),
    )
    engine = IgnitionEngine(core, quiet_ignition, config.workspace, config.lifecycle)
    symbol = core.add_abstract_symbol({"benchmark"}, uid="S_TICK_BENCH")
    template = core.add_template(
        Domain.C, core.ref(symbol.uid), (ActantRole.SUBJECT,), uid="T_TICK_BENCH"
    )

    # n hypernodes + (n-1) FOLLOW links >= target_graph_units.
    n_count = (target_graph_units + 2) // 2
    nodes = []
    for index in range(n_count):
        entity = core.add_entity(
            Domain.C, {"name": Property("name", f"bench-{index}", "str")}
        )
        node, _ = core.add_hypernode(
            Domain.C,
            core.ref(template.uid),
            {ActantRole.SUBJECT: core.ref(entity.uid)},
            0.4,
            deduplicate=False,
            count_occurrence=False,
        )
        nodes.append(node)
    for left, right in zip(nodes, nodes[1:]):
        core.add_link("FOLLOW", core.ref(left.uid), core.ref(right.uid), 0.2)

    graph_units = len(nodes) + max(0, len(nodes) - 1)
    engine.seed(core.ref(symbol.uid), config.ignition.seeds.query_recall, reason=SeedReason.QUERY_RECALL)
    for _ in range(warmup_ticks):
        engine.tick(include_pacemaker=False)

    # Do not charge the benchmark for cyclic garbage left by unrelated callers.
    # Garbage produced by measured ticks remains part of the measured workload.
    gc.collect()
    samples: list[float] = []
    for _ in range(measured_ticks):
        started = perf_counter()
        engine.tick(include_pacemaker=False)
        samples.append((perf_counter() - started) * 1000.0)
    ordered = sorted(samples)
    p95_index = min(len(ordered) - 1, max(0, int(0.95 * len(ordered) + 0.999999) - 1))
    max_ms = max(samples)
    return TickBenchmarkReport(
        graph_units_n_plus_l=graph_units,
        canonical_uids=len(core.store.all_uids()),
        measured_ticks=measured_ticks,
        warmup_ticks=warmup_ticks,
        mean_ms=sum(samples) / len(samples),
        max_ms=max_ms,
        p95_ms=ordered[p95_index],
        passes_500ms=max_ms <= 500.0,
    )
