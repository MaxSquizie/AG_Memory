from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Any, Mapping, Sequence
import json

from ah.config import AppConfig
from ah.core import AHCore
from ah.core.persistence import _ref, _serialize_element
from ah.diagnostics.document_acceptance import (
    DocumentSpec,
    evaluate_document_graph,
    load_document_specs,
)
from ah.diagnostics.hackathon_metrics import (
    M2QuestionObservation,
    M4Report,
    score_m2_explainability,
    score_m4_comparison,
)
from ah.llm.embeddings import EmbeddingClient, build_embedding_client
from rag.vanilla import (
    RAG_DEFAULT_TOP_K,
    GenerativeBackend,
    VanillaRag,
    VanillaRagIndex,
    is_unknown_answer,
    normalize_text,
    rag_hallucinated,
)
from ah.model import RefKind


M4_RUNS_DIRNAME = "m4_runs"
DEFAULT_M4_QUESTIONS = "m4_questions.json"
M2_D_MAX = 6


class M4AcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class M4Question:
    question_id: str
    document_id: str
    text: str
    path: tuple[str, ...]
    depth: int
    must_contain: tuple[str, ...]
    gold_spans: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class InjectedAhAnswer:
    answer: str
    used_uids: tuple[str, ...] = ()
    used_fact_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class M4CaseRecord:
    question_id: str
    document_id: str
    text: str
    side: str
    answer: str
    depth: int
    correct: bool
    trace_complete: bool
    hallucinated: bool
    used_uids: tuple[str, ...] = ()
    used_fact_ids: tuple[str, ...] = ()
    chunk_ids: tuple[str, ...] = ()
    retrieved_texts: tuple[str, ...] = ()
    expected_path: tuple[str, ...] = ()
    must_contain: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True, slots=True)
class M4AcceptanceReport:
    passed: bool
    error: str | None
    output_dir: str | None
    question_count: int
    ah_explainability: float | None
    rag_explainability: float | None
    ah_hallucination: float | None
    rag_hallucination: float | None
    m4: M4Report | None
    elapsed_ms: float
    embed_model: str = ""
    top_k: int = RAG_DEFAULT_TOP_K
    chunk_count: int = 0
    backend: str = ""
    ah_cases: tuple[M4CaseRecord, ...] = ()
    rag_cases: tuple[M4CaseRecord, ...] = ()


def load_m4_questions(path: str | Path) -> tuple[M4Question, ...]:
    source = Path(path)
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or int(payload.get("version") or 0) != 1:
        raise M4AcceptanceError("m4_questions.json must be an object with version=1")
    raw_questions = payload.get("questions")
    if not isinstance(raw_questions, list) or not raw_questions:
        raise M4AcceptanceError("m4_questions.json requires a non-empty questions list")
    questions: list[M4Question] = []
    seen: set[str] = set()
    for index, raw in enumerate(raw_questions, 1):
        if not isinstance(raw, dict):
            raise M4AcceptanceError(f"m4 question #{index} must be an object")
        question_id = str(raw.get("id") or f"q{index}").strip()
        document_id = str(raw.get("document_id") or "").strip()
        text = str(raw.get("text") or "").strip()
        path_ids = tuple(str(item).strip() for item in (raw.get("path") or []) if str(item).strip())
        if question_id in seen:
            raise M4AcceptanceError(f"Duplicate m4 question id: {question_id}")
        if not document_id or not text or len(path_ids) < 2:
            raise M4AcceptanceError(f"m4 question {question_id} requires document_id, text, and path")
        seen.add(question_id)
        raw_depth = raw.get("depth")
        depth = int(raw_depth) if raw_depth is not None else max(1, len(path_ids) - 1)
        questions.append(
            M4Question(
                question_id=question_id,
                document_id=document_id,
                text=text,
                path=path_ids,
                depth=max(1, depth),
                must_contain=tuple(str(item).strip() for item in (raw.get("must_contain") or []) if str(item).strip()),
                gold_spans=tuple(str(item).strip() for item in (raw.get("gold_spans") or []) if str(item).strip()),
            )
        )
    return tuple(questions)


def ah_hallucinated(
    answer: str,
    used_uids: Sequence[str],
    expected_uids: Sequence[str],
    corpus_uids: Sequence[str],
) -> bool:
    if is_unknown_answer(answer):
        return False
    used = {str(item) for item in used_uids if str(item)}
    expected = {str(item) for item in expected_uids if str(item)}
    corpus = {str(item) for item in corpus_uids if str(item)}
    if not used:
        return True
    if corpus and not (used & corpus):
        return True
    if expected and not (used & expected):
        return True
    return False


def ah_correct(
    answer: str,
    must_contain: Sequence[str],
    used_ids: Sequence[str],
    expected_ids: Sequence[str],
) -> bool:
    if is_unknown_answer(answer):
        return False
    answer_norm = normalize_text(answer)
    anchors = [normalize_text(item) for item in must_contain if normalize_text(item)]
    if anchors and all(item in answer_norm for item in anchors):
        return True
    return bool(set(used_ids) & set(expected_ids))


def ah_trace_complete(used_ids: Sequence[str], expected_ids: Sequence[str]) -> bool:
    expected = {str(item) for item in expected_ids if str(item)}
    if not expected:
        return False
    return expected.issubset({str(item) for item in used_ids if str(item)})


def run_m4_acceptance(
    config: AppConfig,
    *,
    data_dir: str | Path | None = None,
    questions_file: str | Path | None = None,
    embedder: EmbeddingClient | None = None,
    generator: GenerativeBackend | None = None,
    ah_answers: Mapping[str, InjectedAhAnswer] | None = None,
    top_k: int = RAG_DEFAULT_TOP_K,
    output_dir: str | Path | None = None,
) -> M4AcceptanceReport:
    started = perf_counter()
    root = Path(data_dir) if data_dir is not None else Path(config.paths.data_dir)
    bundle_root = Path(output_dir) if output_dir is not None else root
    questions_path = Path(questions_file) if questions_file is not None else root / DEFAULT_M4_QUESTIONS
    embed_model = config.llm.embedding_model_name()
    backend_name = str(config.llm.backend or "").strip()
    error: str | None = None
    questions: tuple[M4Question, ...] = ()
    specs: tuple[DocumentSpec, ...] = ()
    index: VanillaRagIndex | None = None
    ah_cases: list[M4CaseRecord] = []
    rag_cases: list[M4CaseRecord] = []
    report: M4AcceptanceReport | None = None
    try:
        questions = load_m4_questions(questions_path)
        specs = load_document_specs(root)
        _validate_questions_against_specs(questions, specs)
        active_embedder = embedder or build_embedding_client(config)
        rag = VanillaRag(active_embedder, generator, top_k=top_k, embed_model=embed_model)
        index = rag.build_index(specs)
        live_generator = generator
        isolated = None
        if ah_answers is None or live_generator is None:
            isolated = _build_isolated_services(config)
            if live_generator is None:
                live_generator = isolated.llm
                rag = VanillaRag(active_embedder, live_generator, top_k=top_k, embed_model=embed_model)
            if ah_answers is None:
                ah_cases = list(_run_ah_branch(isolated, specs, questions))
        if ah_answers is not None:
            ah_cases = list(_records_from_injected(questions, ah_answers))
        if live_generator is None:
            raise M4AcceptanceError("LLM backend is unavailable for M4 RAG generate")
        rag.generator = live_generator
        rag_cases = list(_run_rag_branch(rag, index, questions))
        report = _score_report(
            questions,
            ah_cases,
            rag_cases,
            embed_model=embed_model,
            top_k=top_k,
            chunk_count=len(index.chunks) if index is not None else 0,
            backend=backend_name,
            elapsed_ms=(perf_counter() - started) * 1000.0,
        )
    except Exception as exc:
        error = str(exc)
        report = M4AcceptanceReport(
            passed=False,
            error=error,
            output_dir=None,
            question_count=len(questions),
            ah_explainability=None,
            rag_explainability=None,
            ah_hallucination=None,
            rag_hallucination=None,
            m4=None,
            elapsed_ms=(perf_counter() - started) * 1000.0,
            embed_model=embed_model,
            top_k=top_k,
            chunk_count=len(index.chunks) if index is not None else 0,
            backend=backend_name,
            ah_cases=tuple(ah_cases),
            rag_cases=tuple(rag_cases),
        )
    finally:
        output_dir = _write_m4_bundle(
            bundle_root,
            report=report if report is not None else M4AcceptanceReport(
                False, error or "M4 harness aborted", None, len(questions),
                None, None, None, None, None, (perf_counter() - started) * 1000.0,
                embed_model, top_k, len(index.chunks) if index is not None else 0, backend_name,
                tuple(ah_cases), tuple(rag_cases),
            ),
            config=config,
            questions=questions,
            specs=specs,
            index=index,
            questions_path=questions_path,
        )
    return replace(report, output_dir=str(output_dir))


def _validate_questions_against_specs(
    questions: Sequence[M4Question],
    specs: Sequence[DocumentSpec],
) -> None:
    by_id = {spec.document_id: spec for spec in specs}
    for question in questions:
        spec = by_id.get(question.document_id)
        if spec is None:
            raise M4AcceptanceError(f"m4 question {question.question_id} references unknown document {question.document_id}")
        oracle_texts = {str(item.get("text") or "").strip() for item in spec.m2_questions}
        if question.text not in oracle_texts:
            raise M4AcceptanceError(
                f"m4 question {question.question_id} text is not a document m2_question"
            )
        fact_ids = {
            str(item.get("id") or "").strip()
            for item in (spec.final_expectation.get("facts") or [])
            if isinstance(item, dict)
        }
        missing = [item for item in question.path if item not in fact_ids]
        if missing:
            raise M4AcceptanceError(
                f"m4 question {question.question_id} path references unknown facts: {', '.join(missing)}"
            )


def _build_isolated_services(config: AppConfig):
    from ah.bootstrap import RuntimeServices

    isolated_config = replace(
        config,
        persistence=replace(config.persistence, enabled=False, load_on_start=False),
    )
    services = RuntimeServices.build(isolated_config, core=AHCore())
    if services.llm is None:
        raise M4AcceptanceError("LLM backend is disabled; M4 cannot score AH or RAG")
    if not services.llm.is_running:
        services.llm.start()
    return services


def _run_ah_branch(
    services: Any,
    specs: Sequence[DocumentSpec],
    questions: Sequence[M4Question],
) -> tuple[M4CaseRecord, ...]:
    orchestrator = services.create_orchestrator()
    fact_maps: dict[str, dict[str, str]] = {}
    corpus_uids: dict[str, tuple[str, ...]] = {}
    by_id = {spec.document_id: spec for spec in specs}
    needed = {question.document_id for question in questions}
    for document_id in needed:
        spec = by_id[document_id]
        for paragraph in spec.paragraphs:
            orchestrator.handle_user_text(paragraph.text)
        snapshot = core_snapshot_map(services.core)
        _, matched = evaluate_document_graph(snapshot, spec.final_expectation)
        fact_maps[document_id] = dict(matched)
        corpus_uids[document_id] = tuple(snapshot.keys())
    records: list[M4CaseRecord] = []
    for question in questions:
        turn = orchestrator.handle_user_text(question.text)
        used_uids = _collect_turn_uids(turn)
        matched = fact_maps.get(question.document_id) or {}
        reverse = {uid: fact_id for fact_id, uid in matched.items()}
        used_fact_ids = tuple(reverse[uid] for uid in used_uids if uid in reverse)
        expected_uids = tuple(matched[fid] for fid in question.path if fid in matched)
        answer = str(turn.response_text or "").strip() or "UNKNOWN"
        used_ids = tuple(dict.fromkeys((*used_uids, *used_fact_ids)))
        expected_ids = tuple(dict.fromkeys((*expected_uids, *question.path)))
        records.append(
            M4CaseRecord(
                question_id=question.question_id,
                document_id=question.document_id,
                text=question.text,
                side="ah",
                answer=answer,
                depth=_score_depth(question.depth),
                correct=ah_correct(answer, question.must_contain, used_ids, expected_ids),
                trace_complete=ah_trace_complete(used_ids, question.path) or ah_trace_complete(used_uids, expected_uids),
                hallucinated=ah_hallucinated(
                    answer,
                    used_uids,
                    expected_uids,
                    corpus_uids.get(question.document_id, ()),
                ),
                used_uids=used_uids,
                used_fact_ids=used_fact_ids,
                expected_path=question.path,
                must_contain=question.must_contain,
            )
        )
    return tuple(records)


def _run_rag_branch(
    rag: VanillaRag,
    index: VanillaRagIndex,
    questions: Sequence[M4Question],
) -> tuple[M4CaseRecord, ...]:
    records: list[M4CaseRecord] = []
    for question in questions:
        result = rag.answer(question.text, index)
        answer = result.answer
        records.append(
            M4CaseRecord(
                question_id=question.question_id,
                document_id=question.document_id,
                text=question.text,
                side="rag",
                answer=answer,
                depth=_score_depth(question.depth),
                correct=(
                    not is_unknown_answer(answer)
                    and all(normalize_text(item) in normalize_text(answer) for item in question.must_contain)
                ),
                trace_complete=False,
                hallucinated=rag_hallucinated(answer, result.retrieved_texts, question.must_contain),
                chunk_ids=result.chunk_ids,
                retrieved_texts=result.retrieved_texts,
                expected_path=question.path,
                must_contain=question.must_contain,
            )
        )
    return tuple(records)


def _records_from_injected(
    questions: Sequence[M4Question],
    ah_answers: Mapping[str, InjectedAhAnswer],
) -> tuple[M4CaseRecord, ...]:
    records: list[M4CaseRecord] = []
    for question in questions:
        injected = ah_answers.get(question.question_id)
        if injected is None:
            raise M4AcceptanceError(f"injected AH answers missing {question.question_id}")
        used_ids = tuple(dict.fromkeys((*injected.used_uids, *injected.used_fact_ids)))
        records.append(
            M4CaseRecord(
                question_id=question.question_id,
                document_id=question.document_id,
                text=question.text,
                side="ah",
                answer=injected.answer,
                depth=_score_depth(question.depth),
                correct=ah_correct(injected.answer, question.must_contain, used_ids, question.path),
                trace_complete=ah_trace_complete(injected.used_fact_ids or injected.used_uids, question.path),
                hallucinated=ah_hallucinated(
                    injected.answer,
                    injected.used_uids or injected.used_fact_ids,
                    question.path,
                    injected.used_uids or question.path,
                ),
                used_uids=injected.used_uids,
                used_fact_ids=injected.used_fact_ids,
                expected_path=question.path,
                must_contain=question.must_contain,
            )
        )
    return tuple(records)


def _score_report(
    questions: Sequence[M4Question],
    ah_cases: Sequence[M4CaseRecord],
    rag_cases: Sequence[M4CaseRecord],
    *,
    embed_model: str,
    top_k: int,
    chunk_count: int,
    backend: str,
    elapsed_ms: float,
) -> M4AcceptanceReport:
    if len(ah_cases) != len(questions) or len(rag_cases) != len(questions):
        raise M4AcceptanceError("M4 harness produced an incomplete case set")
    ah_obs = tuple(
        M2QuestionObservation(item.correct, item.depth, item.trace_complete, item.question_id)
        for item in ah_cases
    )
    rag_obs = tuple(
        M2QuestionObservation(item.correct, item.depth, item.trace_complete, item.question_id)
        for item in rag_cases
    )
    ah_m2 = score_m2_explainability(ah_obs, d_max=M2_D_MAX, expected_count=len(questions))
    rag_m2 = score_m2_explainability(rag_obs, d_max=M2_D_MAX, expected_count=len(questions))
    ah_h = sum(1.0 for item in ah_cases if item.hallucinated) / len(ah_cases)
    rag_h = sum(1.0 for item in rag_cases if item.hallucinated) / len(rag_cases)
    m4 = score_m4_comparison(
        ah_explainability=ah_m2.explain_score,
        rag_explainability=rag_m2.explain_score,
        ah_hallucination=ah_h,
        rag_hallucination=rag_h,
    )
    return M4AcceptanceReport(
        passed=True,
        error=None,
        output_dir=None,
        question_count=len(questions),
        ah_explainability=ah_m2.explain_score,
        rag_explainability=rag_m2.explain_score,
        ah_hallucination=ah_h,
        rag_hallucination=rag_h,
        m4=m4,
        elapsed_ms=elapsed_ms,
        embed_model=embed_model,
        top_k=top_k,
        chunk_count=chunk_count,
        backend=backend,
        ah_cases=tuple(ah_cases),
        rag_cases=tuple(rag_cases),
    )


def _score_depth(depth: int) -> int:
    return max(1, min(int(depth), M2_D_MAX))


def _collect_turn_uids(turn: Any) -> tuple[str, ...]:
    uids: list[str] = []
    for execution in getattr(turn, "queries", ()) or ():
        outcome = getattr(execution, "outcome", None)
        if outcome is None:
            continue
        for ref in tuple(getattr(outcome, "uid_trace", ()) or ()) + tuple(getattr(outcome, "premise_refs", ()) or ()):
            uid = getattr(ref, "uid", None)
            if uid:
                uids.append(str(uid))
    return tuple(dict.fromkeys(uids))


def core_snapshot_map(core: AHCore) -> dict[str, dict[str, Any]]:
    snapshot: dict[str, dict[str, Any]] = {}
    for uid in core.store.all_uids():
        kind = core.store.kind_of(uid)
        if kind is RefKind.S:
            symbol = core.store.get_symbol(uid)
            snapshot[uid] = {"uid": uid, "kind": "S", "forms": sorted(symbol.forms)}
        elif kind is RefKind.L:
            link = core.store.get_link(uid)
            snapshot[uid] = {
                "uid": uid,
                "kind": "L",
                "relation_id": link.relation_id,
                "weight": link.weight,
                "source": _ref(link.source),
                "target": _ref(link.target),
            }
        else:
            domain = core.store.domain_of(uid)
            if domain is None:
                continue
            snapshot[uid] = _serialize_element(domain, core.store.get_element_any_domain(uid))
    return snapshot


def _write_m4_bundle(
    data_dir: Path,
    *,
    report: M4AcceptanceReport,
    config: AppConfig,
    questions: Sequence[M4Question],
    specs: Sequence[DocumentSpec],
    index: VanillaRagIndex | None,
    questions_path: Path,
) -> Path:
    timestamp = datetime.now().astimezone().strftime("%Y%m%d_%H%M%S_%z")
    root = Path(data_dir) / M4_RUNS_DIRNAME
    output_dir = root / timestamp
    suffix = 1
    while output_dir.exists():
        output_dir = root / f"{timestamp}_{suffix:02d}"
        suffix += 1
    output_dir.mkdir(parents=True, exist_ok=False)
    summary = asdict(replace(report, output_dir=str(output_dir)))
    (output_dir / "summary.json").write_text(
        json.dumps(_jsonable(summary), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    lines = [
        f"M4 {'OK' if report.passed else 'ERROR'}",
        f"questions={report.question_count}",
        f"backend={report.backend}",
        f"embed_model={report.embed_model}",
        f"top_k={report.top_k}",
        f"chunks={report.chunk_count}",
        f"elapsed_ms={report.elapsed_ms:.2f}",
    ]
    if report.error:
        lines.append(f"error={report.error}")
    if report.m4 is not None:
        lines.extend(
            [
                f"ExplainScore_AH={report.ah_explainability}",
                f"ExplainScore_RAG={report.rag_explainability}",
                f"Hallucination_AH={report.ah_hallucination}",
                f"Hallucination_RAG={report.rag_hallucination}",
                f"delta_explainability={report.m4.delta_explainability}",
                f"delta_hallucination={report.m4.delta_hallucination}",
            ]
        )
    (output_dir / "report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    (output_dir / "config_snapshot.json").write_text(
        json.dumps(
            {
                "backend": config.llm.backend,
                "ollama_model": config.llm.ollama_model,
                "ollama_embed_model": config.llm.ollama_embed_model,
                "lmstudio_model": config.llm.lmstudio_model,
                "lmstudio_embed_model": config.llm.lmstudio_embed_model,
                "embed_model": report.embed_model,
                "top_k": report.top_k,
                "questions_file": str(questions_path),
                "corpus_paths": [str(spec.source_file) for spec in specs],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    (output_dir / "questions.json").write_text(
        json.dumps([asdict(item) for item in questions], ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_jsonl(output_dir / "ah_cases.jsonl", report.ah_cases)
    _write_jsonl(output_dir / "rag_cases.jsonl", report.rag_cases)
    counts: dict[str, int] = {}
    if index is not None:
        for chunk in index.chunks:
            counts[chunk.document_id] = counts.get(chunk.document_id, 0) + 1
    (output_dir / "index_manifest.json").write_text(
        json.dumps(
            {
                "embed_model": report.embed_model,
                "chunk_count": report.chunk_count,
                "documents": counts,
                "chunk_ids": [chunk.chunk_id for chunk in (index.chunks if index is not None else ())],
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    return output_dir


def _write_jsonl(path: Path, rows: Sequence[M4CaseRecord]) -> None:
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(_jsonable(asdict(row)), ensure_ascii=False) + "\n")


def _jsonable(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if hasattr(value, "__dict__") or is_dataclass_instance(value):
        return _jsonable(asdict(value) if is_dataclass_instance(value) else vars(value))
    return repr(value)


def is_dataclass_instance(value: Any) -> bool:
    from dataclasses import is_dataclass

    return is_dataclass(value) and not isinstance(value, type)
