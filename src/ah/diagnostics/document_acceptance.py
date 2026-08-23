from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
import json
from pathlib import Path
import re
from typing import Any, Mapping, MutableMapping, Sequence, TYPE_CHECKING

from ah.diagnostics.acceptance_runner import AcceptanceRunResult, run_acceptance_suite
from ah.diagnostics.semantic_oracle import apply_ah_diff

if TYPE_CHECKING:
    from ah.bootstrap import RuntimeServices


DEFAULT_DOCUMENT_ORACLE = "document_acceptance/oracle.json"
DOCUMENT_RUNS_DIRNAME = "document_acceptance_runs"


class DocumentAcceptanceError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class DocumentParagraph:
    document_id: str
    document_title: str
    paragraph_index: int
    text: str
    expectation: Mapping[str, Any]
    family: str
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DocumentSpec:
    document_id: str
    title: str
    source_file: Path
    paragraphs: tuple[DocumentParagraph, ...]
    final_expectation: Mapping[str, Any]
    m2_questions: tuple[Mapping[str, Any], ...]
    ingest_mode: str = "paragraphs"
    source_text: str = ""


@dataclass(frozen=True, slots=True)
class DocumentVerdict:
    document_id: str
    title: str
    status: str
    paragraph_passed: int
    paragraph_total: int
    runtime_errors: int
    graph_checks: tuple[Mapping[str, Any], ...]
    m2_question_count: int

    @property
    def failures(self) -> tuple[Mapping[str, Any], ...]:
        return tuple(item for item in self.graph_checks if not bool(item.get("ok")))


@dataclass(frozen=True, slots=True)
class DocumentAcceptanceRunResult:
    output_dir: Path
    total_documents: int
    passed_documents: int
    failed_documents: int
    total_paragraphs: int
    paragraph_semantic_passed: int
    paragraph_semantic_failed: int
    runtime_errors: int
    verdicts: tuple[DocumentVerdict, ...]
    underlying: AcceptanceRunResult


def _norm(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def _split_paragraphs(text: str) -> tuple[str, ...]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    chunks = [re.sub(r"\s+", " ", chunk).strip() for chunk in re.split(r"\n\s*\n", normalized)]
    return tuple(chunk for chunk in chunks if chunk)


def _split_monolith_sentences(text: str) -> tuple[str, ...]:
    """Split one source monolith only at explicit sentence boundaries.

    This is an ingestion boundary, not semantic parsing.  It does not use an LLM,
    entity state, causal labels or AH contents.  The source document remains one
    scenario; the bounded perception parser simply receives consecutive windows
    while AH/InteractionContext/Ignition stay continuous.
    """
    normalized = re.sub(r"\s+", " ", text.replace("\r", " ").replace("\n", " ")).strip()
    if not normalized:
        return ()
    # The document acceptance corpus deliberately avoids abbreviations ending in a
    # dot.  Keep closing quotes/brackets with the sentence and split only when the
    # next token begins a new sentence.  Ellipsis is treated as terminal punctuation.
    parts = re.split(
        r'(?<=[.!?…][»”"\)\]])\s+'
        r'|(?<=[.!?…])\s+(?=—\s+[«„"А-ЯЁA-Z0-9])'
        r'|(?<=[.!?…])\s+(?=[«„"А-ЯЁA-Z0-9])',
        normalized,
    )
    return tuple(part.strip() for part in parts if part.strip())


def _pack_monolith_windows(text: str, sentences_per_window: int) -> tuple[str, ...]:
    if sentences_per_window <= 0:
        raise DocumentAcceptanceError("monolith sentences_per_window must be > 0")
    sentences = _split_monolith_sentences(text)
    return tuple(
        " ".join(sentences[index:index + sentences_per_window])
        for index in range(0, len(sentences), sentences_per_window)
    )


def load_document_specs(data_dir: str | Path, oracle_file: str | Path | None = None) -> tuple[DocumentSpec, ...]:
    root = Path(data_dir)
    source = Path(oracle_file) if oracle_file is not None else root / DEFAULT_DOCUMENT_ORACLE
    if not source.is_file():
        raise FileNotFoundError(f"Document acceptance oracle not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise DocumentAcceptanceError("Document acceptance oracle must be an object with version=1")
    raw_documents = payload.get("documents")
    if not isinstance(raw_documents, list) or not raw_documents:
        raise DocumentAcceptanceError("Document acceptance oracle requires a non-empty documents list")

    result: list[DocumentSpec] = []
    seen_ids: set[str] = set()
    for doc_index, raw_doc in enumerate(raw_documents, 1):
        if not isinstance(raw_doc, dict):
            raise DocumentAcceptanceError(f"Document #{doc_index} must be an object")
        document_id = str(raw_doc.get("id") or "").strip()
        title = str(raw_doc.get("title") or document_id).strip()
        relative_file = str(raw_doc.get("file") or "").strip()
        if not document_id or not relative_file:
            raise DocumentAcceptanceError(f"Document #{doc_index} requires id and file")
        if document_id in seen_ids:
            raise DocumentAcceptanceError(f"Duplicate document id: {document_id}")
        seen_ids.add(document_id)
        source_file = source.parent / relative_file
        if not source_file.is_file():
            raise FileNotFoundError(f"Document text not found: {source_file}")
        source_text = source_file.read_text(encoding="utf-8-sig")
        ingest = raw_doc.get("ingest") or {}
        if not isinstance(ingest, dict):
            raise DocumentAcceptanceError(f"Document {document_id} ingest must be an object")
        ingest_mode = str(ingest.get("mode") or "paragraphs").strip().casefold()
        if ingest_mode == "paragraphs":
            text_paragraphs = _split_paragraphs(source_text)
        elif ingest_mode == "monolith":
            sentences_per_window = int(ingest.get("sentences_per_window", 2))
            text_paragraphs = _pack_monolith_windows(source_text, sentences_per_window)
        else:
            raise DocumentAcceptanceError(
                f"Document {document_id} unsupported ingest mode: {ingest_mode}"
            )
        raw_paragraphs = raw_doc.get("units", raw_doc.get("paragraphs"))
        if not isinstance(raw_paragraphs, list) or not raw_paragraphs:
            raise DocumentAcceptanceError(f"Document {document_id} requires unit expectations")
        if len(text_paragraphs) != len(raw_paragraphs):
            raise DocumentAcceptanceError(
                f"Document {document_id} unit count mismatch: text={len(text_paragraphs)}, oracle={len(raw_paragraphs)}"
            )
        paragraphs: list[DocumentParagraph] = []
        for paragraph_index, (paragraph_text, raw_paragraph) in enumerate(zip(text_paragraphs, raw_paragraphs), 1):
            if not isinstance(raw_paragraph, dict):
                raise DocumentAcceptanceError(f"{document_id} paragraph #{paragraph_index} must be an object")
            expectation = raw_paragraph.get("expect", {})
            if not isinstance(expectation, dict):
                raise DocumentAcceptanceError(f"{document_id} paragraph #{paragraph_index} expect must be an object")
            family = str(raw_paragraph.get("family") or "document").strip() or "document"
            raw_tags = raw_paragraph.get("tags") or []
            if not isinstance(raw_tags, list) or any(not isinstance(item, str) for item in raw_tags):
                raise DocumentAcceptanceError(f"{document_id} paragraph #{paragraph_index} tags must be strings")
            paragraphs.append(
                DocumentParagraph(
                    document_id=document_id,
                    document_title=title,
                    paragraph_index=paragraph_index,
                    text=paragraph_text,
                    expectation=expectation,
                    family=family,
                    tags=tuple(str(item).strip() for item in raw_tags if str(item).strip()),
                )
            )
        final_expectation = raw_doc.get("final", {})
        if not isinstance(final_expectation, dict):
            raise DocumentAcceptanceError(f"Document {document_id} final must be an object")
        raw_questions = raw_doc.get("m2_questions") or []
        if not isinstance(raw_questions, list) or any(not isinstance(item, dict) for item in raw_questions):
            raise DocumentAcceptanceError(f"Document {document_id} m2_questions must be objects")
        _validate_final_oracle(document_id, final_expectation, raw_questions)
        result.append(
            DocumentSpec(
                document_id=document_id,
                title=title,
                source_file=source_file,
                paragraphs=tuple(paragraphs),
                final_expectation=final_expectation,
                m2_questions=tuple(raw_questions),
                ingest_mode=ingest_mode,
                source_text=source_text,
            )
        )
    return tuple(result)


def _validate_final_oracle(document_id: str, final: Mapping[str, Any], questions: Sequence[Mapping[str, Any]]) -> None:
    raw_facts = final.get("facts") or []
    raw_links = final.get("links") or []
    raw_forbidden = final.get("forbidden_links") or []
    raw_forbidden_facts = final.get("forbidden_facts") or []
    if not isinstance(raw_facts, list) or any(not isinstance(item, dict) for item in raw_facts):
        raise DocumentAcceptanceError(f"Document {document_id} final.facts must be objects")
    if not isinstance(raw_links, list) or any(not isinstance(item, dict) for item in raw_links):
        raise DocumentAcceptanceError(f"Document {document_id} final.links must be objects")
    if not isinstance(raw_forbidden, list) or any(not isinstance(item, dict) for item in raw_forbidden):
        raise DocumentAcceptanceError(f"Document {document_id} final.forbidden_links must be objects")
    if not isinstance(raw_forbidden_facts, list) or any(not isinstance(item, dict) for item in raw_forbidden_facts):
        raise DocumentAcceptanceError(f"Document {document_id} final.forbidden_facts must be objects")
    for index, item in enumerate(raw_forbidden_facts, 1):
        predicate = str(item.get("predicate") or "").strip()
        if not predicate:
            raise DocumentAcceptanceError(
                f"Document {document_id} forbidden fact #{index} requires predicate"
            )
        roles = item.get("roles") or {}
        if not isinstance(roles, dict):
            raise DocumentAcceptanceError(
                f"Document {document_id} forbidden fact #{index} roles must be an object"
            )
    fact_ids: set[str] = set()
    for item in raw_facts:
        fact_id = str(item.get("id") or "").strip()
        predicate = str(item.get("predicate") or "").strip()
        if not fact_id or not predicate:
            raise DocumentAcceptanceError(f"Document {document_id} every final fact requires id and predicate")
        if fact_id in fact_ids:
            raise DocumentAcceptanceError(f"Document {document_id} duplicate fact id: {fact_id}")
        fact_ids.add(fact_id)
        roles = item.get("roles") or {}
        if not isinstance(roles, dict):
            raise DocumentAcceptanceError(f"Document {document_id} fact {fact_id} roles must be an object")
    for bucket_name, bucket in (("links", raw_links), ("forbidden_links", raw_forbidden)):
        for item in bucket:
            source = str(item.get("source") or "")
            target = str(item.get("target") or "")
            relation = str(item.get("relation") or "").strip().upper()
            if source not in fact_ids or target not in fact_ids or not relation:
                raise DocumentAcceptanceError(
                    f"Document {document_id} final.{bucket_name} references unknown facts or relation: {item}"
                )
    for q_index, question in enumerate(questions, 1):
        text = str(question.get("text") or "").strip()
        path = question.get("path") or []
        relations = question.get("relations") or []
        if not text or not isinstance(path, list) or len(path) < 2:
            raise DocumentAcceptanceError(f"Document {document_id} m2 question #{q_index} needs text and path")
        if any(str(item) not in fact_ids for item in path):
            raise DocumentAcceptanceError(f"Document {document_id} m2 question #{q_index} path references unknown fact")
        if not isinstance(relations, list) or len(relations) != len(path) - 1:
            raise DocumentAcceptanceError(
                f"Document {document_id} m2 question #{q_index} relations must match path edges"
            )


def _compiled_bundle(specs: Sequence[DocumentSpec], target_dir: Path) -> tuple[Path, Path]:
    target_dir.mkdir(parents=True, exist_ok=True)
    cases_file = target_dir / "compiled_cases.txt"
    oracle_file = target_dir / "compiled_oracle.json"
    case_lines: list[str] = []
    oracle_cases: list[dict[str, Any]] = []
    index = 0
    for spec in specs:
        case_lines.append(f"# DOCUMENT {spec.document_id}: {spec.title}")
        for paragraph in spec.paragraphs:
            index += 1
            case_lines.append(paragraph.text)
            oracle_cases.append(
                {
                    "text": paragraph.text,
                    "grade": "EXACT",
                    "scenario": spec.document_id,
                    "family": paragraph.family,
                    "tags": list(paragraph.tags),
                    "note": f"{spec.title}, paragraph {paragraph.paragraph_index}",
                    "expect": paragraph.expectation,
                }
            )
    cases_file.write_text("\n".join(case_lines) + "\n", encoding="utf-8", newline="\n")
    oracle_file.write_text(
        json.dumps({"version": 1, "cases": oracle_cases}, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return cases_file, oracle_file


def _entity_name(snapshot: Mapping[str, Mapping[str, Any]], uid: str) -> str | None:
    item = snapshot.get(uid)
    if not isinstance(item, dict) or item.get("kind") != "M":
        return None
    props = item.get("properties") or {}
    name = props.get("name") if isinstance(props, dict) else None
    if isinstance(name, dict) and name.get("value") is not None:
        return str(name.get("value"))
    return None


def _predicate_forms(snapshot: Mapping[str, Mapping[str, Any]], node: Mapping[str, Any]) -> tuple[str, ...]:
    template_ref = node.get("template")
    if not isinstance(template_ref, dict):
        return ()
    template = snapshot.get(str(template_ref.get("uid") or ""))
    if not isinstance(template, dict) or template.get("kind") != "T":
        return ()
    predicate_ref = template.get("predicate")
    if not isinstance(predicate_ref, dict):
        return ()
    symbol = snapshot.get(str(predicate_ref.get("uid") or ""))
    if not isinstance(symbol, dict) or symbol.get("kind") != "S":
        return ()
    return tuple(str(item) for item in (symbol.get("forms") or []))


def _role_ref(node: Mapping[str, Any], role: str) -> Mapping[str, Any] | None:
    actants = node.get("actants") or {}
    if not isinstance(actants, dict):
        return None
    value = actants.get(str(role).upper())
    return value if isinstance(value, dict) else None


def _ref_label(snapshot: Mapping[str, Mapping[str, Any]], ref: Mapping[str, Any] | None) -> Any:
    if ref is None:
        return None
    uid = str(ref.get("uid") or "")
    kind = str(ref.get("kind") or "")
    if kind == "M":
        return _entity_name(snapshot, uid) or uid
    if kind == "N":
        node = snapshot.get(uid)
        if isinstance(node, dict):
            return {"uid": uid, "predicate": list(_predicate_forms(snapshot, node))}
    return uid


def _match_target(
    snapshot: Mapping[str, Mapping[str, Any]],
    ref: Mapping[str, Any] | None,
    expected: Any,
    matched: Mapping[str, str],
) -> bool:
    if ref is None:
        return False
    if isinstance(expected, str):
        return _norm(_ref_label(snapshot, ref)) == _norm(expected)
    if not isinstance(expected, dict):
        return False
    if "same_as" in expected:
        path = str(expected["same_as"])
        if "." not in path:
            return False
        fact_id, role = path.split(".", 1)
        other_uid = matched.get(fact_id)
        other_node = snapshot.get(other_uid or "")
        if not isinstance(other_node, dict):
            return False
        other_ref = _role_ref(other_node, role)
        return other_ref is not None and str(other_ref.get("uid")) == str(ref.get("uid"))
    if "fact" in expected:
        return str(ref.get("uid")) == str(matched.get(str(expected["fact"])) or "")
    if "canonical_name" in expected:
        return _norm(_ref_label(snapshot, ref)) == _norm(expected["canonical_name"])
    if "any_of" in expected:
        options = expected.get("any_of") or []
        return any(_norm(_ref_label(snapshot, ref)) == _norm(option) for option in options)
    return False


def _match_fact(
    snapshot: Mapping[str, Mapping[str, Any]],
    spec: Mapping[str, Any],
    matched: Mapping[str, str],
) -> tuple[str | None, list[dict[str, Any]]]:
    predicate = _norm(spec.get("predicate"))
    domain = str(spec.get("domain") or "C").upper()
    roles = spec.get("roles") or {}
    exact_roles = bool(spec.get("exact_roles", True))
    candidates: list[dict[str, Any]] = []
    for uid, node in snapshot.items():
        if not isinstance(node, dict) or node.get("kind") != "N" or str(node.get("domain") or "").upper() != domain:
            continue
        forms = _predicate_forms(snapshot, node)
        if not any(_norm(form) == predicate for form in forms):
            continue
        actual_roles = set((node.get("actants") or {}).keys()) if isinstance(node.get("actants"), dict) else set()
        if exact_roles and actual_roles != {str(role).upper() for role in roles}:
            continue
        if not exact_roles and not {str(role).upper() for role in roles}.issubset(actual_roles):
            continue
        if "semantic_scope" in spec:
            expected_scope = str(spec.get("semantic_scope") or "").strip().upper()
            meta = node.get("meta") or {}
            actual_scope = str(meta.get("semantic_scope") or "").strip().upper() if isinstance(meta, dict) else ""
            if expected_scope in {"", "ASSERTED", "WORLD", "NONE"}:
                if actual_scope:
                    continue
            elif actual_scope != expected_scope:
                continue
        if all(_match_target(snapshot, _role_ref(node, role), expected, matched) for role, expected in roles.items()):
            candidates.append({"uid": uid, "forms": list(forms), "roles": {role: _ref_label(snapshot, _role_ref(node, role)) for role in actual_roles}})
    if len(candidates) == 1:
        return str(candidates[0]["uid"]), candidates
    return None, candidates


def evaluate_document_graph(
    snapshot: Mapping[str, Mapping[str, Any]],
    expectation: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], ...], Mapping[str, str]]:
    checks: list[dict[str, Any]] = []
    matched: dict[str, str] = {}
    for fact in expectation.get("facts") or []:
        fact_id = str(fact.get("id") or "")
        uid, candidates = _match_fact(snapshot, fact, matched)
        checks.append(
            {
                "name": f"fact.{fact_id}",
                "ok": uid is not None,
                "expected": fact,
                "actual": candidates,
            }
        )
        if uid is not None:
            matched[fact_id] = uid

    # Negative fact oracle: a literary/state description must not silently invent
    # a world event (for example, a subjective ``показалось, что...`` or a result
    # participle must not become an asserted external cause).  Matching uses the
    # same semantic fact matcher as positive expectations, but success means *no*
    # canonical N satisfies the forbidden specification.
    for index, fact in enumerate(expectation.get("forbidden_facts") or [], 1):
        uid, candidates = _match_fact(snapshot, fact, matched)
        label = str(fact.get("id") or index)
        checks.append(
            {
                "name": f"forbidden_fact.{label}",
                "ok": uid is None,
                "expected": False,
                "actual": {"matched_uid": uid, "candidates": candidates},
            }
        )

    actual_links = [
        item for item in snapshot.values()
        if isinstance(item, dict) and item.get("kind") == "L"
    ]

    def link_exists(relation: str, source_id: str, target_id: str) -> bool:
        source_uid = matched.get(source_id)
        target_uid = matched.get(target_id)
        if source_uid is None or target_uid is None:
            return False
        for link in actual_links:
            if str(link.get("relation_id") or "").upper() != relation.upper():
                continue
            source = link.get("source") or {}
            target = link.get("target") or {}
            if str(source.get("uid")) == source_uid and str(target.get("uid")) == target_uid:
                return True
        return False

    for link in expectation.get("links") or []:
        relation = str(link.get("relation") or "").upper()
        source_id = str(link.get("source") or "")
        target_id = str(link.get("target") or "")
        exists = link_exists(relation, source_id, target_id)
        checks.append(
            {
                "name": f"link.{relation}.{source_id}->{target_id}",
                "ok": exists,
                "expected": True,
                "actual": exists,
            }
        )
    for link in expectation.get("forbidden_links") or []:
        relation = str(link.get("relation") or "").upper()
        source_id = str(link.get("source") or "")
        target_id = str(link.get("target") or "")
        exists = link_exists(relation, source_id, target_id)
        checks.append(
            {
                "name": f"forbidden_link.{relation}.{source_id}->{target_id}",
                "ok": not exists,
                "expected": False,
                "actual": exists,
            }
        )
    min_cause_depth = expectation.get("min_cause_depth")
    if min_cause_depth is not None:
        cause_edges = {
            (str(item.get("source", {}).get("uid")), str(item.get("target", {}).get("uid")))
            for item in actual_links
            if str(item.get("relation_id") or "").upper() == "CAUSE"
        }
        expected_links = [item for item in expectation.get("links") or [] if str(item.get("relation") or "").upper() == "CAUSE"]
        chain_edges = 0
        for item in expected_links:
            source_uid = matched.get(str(item.get("source") or ""))
            target_uid = matched.get(str(item.get("target") or ""))
            if source_uid and target_uid and (source_uid, target_uid) in cause_edges:
                chain_edges += 1
        checks.append(
            {
                "name": "cause_chain.minimum_depth",
                "ok": chain_edges >= int(min_cause_depth),
                "expected": int(min_cause_depth),
                "actual": chain_edges,
            }
        )
    return tuple(checks), matched


def _graph_category_counts(checks: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, int]]:
    """Aggregate graph-oracle checks into human-readable document capabilities."""
    result = {
        "event_extraction": {"passed": 0, "total": 0},
        "temporal_graph": {"passed": 0, "total": 0},
        "causal_graph": {"passed": 0, "total": 0},
        "negative_constraints": {"passed": 0, "total": 0},
        "other": {"passed": 0, "total": 0},
    }
    for item in checks:
        name = str(item.get("name") or "")
        if name.startswith("fact."):
            bucket = "event_extraction"
        elif name.startswith("link.FOLLOW."):
            bucket = "temporal_graph"
        elif name.startswith("link.CAUSE.") or name == "cause_chain.minimum_depth":
            bucket = "causal_graph"
        elif name.startswith("forbidden_link.") or name.startswith("forbidden_fact."):
            bucket = "negative_constraints"
        else:
            bucket = "other"
        result[bucket]["total"] += 1
        result[bucket]["passed"] += int(bool(item.get("ok")))
    return result


def _scenario_snapshots(run_dir: Path, specs: Sequence[DocumentSpec]) -> Mapping[str, Mapping[str, dict[str, Any]]]:
    initial = json.loads((run_dir / "initial_ah.json").read_text(encoding="utf-8"))
    manifest = json.loads((run_dir / "manifest.json").read_text(encoding="utf-8"))
    snapshot: MutableMapping[str, dict[str, Any]] = deepcopy(initial)
    result: dict[str, Mapping[str, dict[str, Any]]] = {}
    active: str | None = None
    for item in manifest.get("cases") or []:
        scenario = str(item.get("scenario_id") or "")
        if scenario != active:
            snapshot = deepcopy(initial)
            active = scenario
        turn_path = run_dir / str(item.get("file") or f"turn_{int(item['index']):03d}.json")
        if not turn_path.is_file():
            turn_path = run_dir / f"turn_{int(item['index']):03d}.json"
        record = json.loads(turn_path.read_text(encoding="utf-8"))
        apply_ah_diff(snapshot, record.get("ah_diff") or {})
        result[scenario] = deepcopy(snapshot)
    missing = [spec.document_id for spec in specs if spec.document_id not in result]
    if missing:
        raise DocumentAcceptanceError(f"Run bundle lacks scenarios: {', '.join(missing)}")
    return result


def run_document_acceptance(
    services: "RuntimeServices",
    *,
    oracle_file: str | Path | None = None,
) -> DocumentAcceptanceRunResult:
    data_dir = Path(services.config.paths.data_dir)
    specs = load_document_specs(data_dir, oracle_file)
    bundle_dir = data_dir / "document_acceptance" / "compiled"
    cases_file, compiled_oracle = _compiled_bundle(specs, bundle_dir)
    underlying = run_acceptance_suite(
        services,
        cases_file=cases_file,
        oracle_file=compiled_oracle,
        runs_dirname=DOCUMENT_RUNS_DIRNAME,
    )

    ingest_plan = {
        "documents": [
            {
                "id": spec.document_id,
                "title": spec.title,
                "mode": spec.ingest_mode,
                "source_file": str(spec.source_file),
                "source_text": spec.source_text,
                "units": [
                    {"index": item.paragraph_index, "text": item.text}
                    for item in spec.paragraphs
                ],
            }
            for spec in specs
        ]
    }
    (underlying.output_dir / "document_ingest_plan.json").write_text(
        json.dumps(ingest_plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    manifest = json.loads((underlying.output_dir / "manifest.json").read_text(encoding="utf-8"))
    by_scenario: dict[str, list[Mapping[str, Any]]] = {}
    for item in manifest.get("cases") or []:
        by_scenario.setdefault(str(item.get("scenario_id") or ""), []).append(item)
    snapshots = _scenario_snapshots(underlying.output_dir, specs)

    verdicts: list[DocumentVerdict] = []
    for spec in specs:
        paragraph_items = by_scenario.get(spec.document_id, [])
        paragraph_passed = sum(str(item.get("semantic_status")) == "PASS" for item in paragraph_items)
        runtime_errors = sum(str(item.get("status")) != "OK" for item in paragraph_items)
        graph_checks, matched = evaluate_document_graph(snapshots[spec.document_id], spec.final_expectation)
        graph_ok = all(bool(item.get("ok")) for item in graph_checks)
        status = "PASS" if paragraph_passed == len(spec.paragraphs) and runtime_errors == 0 and graph_ok else "FAIL"
        verdicts.append(
            DocumentVerdict(
                document_id=spec.document_id,
                title=spec.title,
                status=status,
                paragraph_passed=paragraph_passed,
                paragraph_total=len(spec.paragraphs),
                runtime_errors=runtime_errors,
                graph_checks=graph_checks,
                m2_question_count=len(spec.m2_questions),
            )
        )
        (underlying.output_dir / f"document_{spec.document_id}_matched_facts.json").write_text(
            json.dumps(matched, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )

    report = {
        "documents": [
            {
                "id": item.document_id,
                "title": item.title,
                "status": item.status,
                "paragraph_passed": item.paragraph_passed,
                "paragraph_total": item.paragraph_total,
                "runtime_errors": item.runtime_errors,
                "m2_question_count": item.m2_question_count,
                "graph_categories": _graph_category_counts(item.graph_checks),
                "graph_checks": list(item.graph_checks),
            }
            for item in verdicts
        ],
        "summary": {
            "documents_total": len(verdicts),
            "documents_passed": sum(item.status == "PASS" for item in verdicts),
            "documents_failed": sum(item.status != "PASS" for item in verdicts),
            "paragraphs_total": underlying.total,
            "paragraphs_semantic_passed": underlying.semantic_passed,
            "paragraphs_semantic_failed": underlying.semantic_failed + underlying.semantic_gaps,
            "runtime_errors": underlying.failed,
        },
    }
    (underlying.output_dir / "document_report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    lines = [
        f"Document acceptance: PASS {report['summary']['documents_passed']}/{report['summary']['documents_total']}",
        f"Paragraph semantic: PASS {underlying.semantic_passed}/{underlying.total} | FAIL {underlying.semantic_failed} | GAP {underlying.semantic_gaps}",
        f"Runtime errors: {underlying.failed}",
        "",
    ]
    for item in verdicts:
        categories = _graph_category_counts(item.graph_checks)
        lines.append(
            f"{item.document_id} {item.status}: {item.title} | paragraphs {item.paragraph_passed}/{item.paragraph_total} | graph {sum(bool(c.get('ok')) for c in item.graph_checks)}/{len(item.graph_checks)} | M2 questions {item.m2_question_count}"
        )
        lines.append(
            "  categories: "
            + " | ".join(
                f"{name} {value['passed']}/{value['total']}"
                for name, value in categories.items()
                if value["total"]
            )
        )
        for failure in item.failures[:8]:
            lines.append(f"  FAIL {failure.get('name')}: expected={failure.get('expected')} actual={failure.get('actual')}")
    (underlying.output_dir / "document_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    return DocumentAcceptanceRunResult(
        output_dir=underlying.output_dir,
        total_documents=len(verdicts),
        passed_documents=sum(item.status == "PASS" for item in verdicts),
        failed_documents=sum(item.status != "PASS" for item in verdicts),
        total_paragraphs=underlying.total,
        paragraph_semantic_passed=underlying.semantic_passed,
        paragraph_semantic_failed=underlying.semantic_failed + underlying.semantic_gaps,
        runtime_errors=underlying.failed,
        verdicts=tuple(verdicts),
        underlying=underlying,
    )
