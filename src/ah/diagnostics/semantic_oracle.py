from __future__ import annotations

from dataclasses import dataclass
from copy import deepcopy
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, MutableMapping, Sequence


DEFAULT_ORACLE_FILENAME = "acceptance_oracle.json"


@dataclass(frozen=True, slots=True)
class SemanticOracleCase:
    index: int
    text: str
    grade: str
    expectation: Mapping[str, Any]
    note: str | None = None
    family: str = "uncategorized"
    tags: tuple[str, ...] = ()
    scenario_id: str = "legacy-sequential"


@dataclass(frozen=True, slots=True)
class SemanticCaseVerdict:
    index: int
    text: str
    status: str
    checks: tuple[dict[str, Any], ...]
    note: str | None = None
    family: str = "uncategorized"
    tags: tuple[str, ...] = ()

    @property
    def failures(self) -> tuple[dict[str, Any], ...]:
        return tuple(item for item in self.checks if not item.get("ok", False))


@dataclass(frozen=True, slots=True)
class SemanticOracleReport:
    total: int
    passed: int
    failed: int
    gaps: int
    cases: tuple[SemanticCaseVerdict, ...]
    family_counts: Mapping[str, Mapping[str, int]]


class SemanticOracleError(RuntimeError):
    pass


def load_semantic_oracle(path: str | Path) -> tuple[SemanticOracleCase, ...]:
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Semantic oracle not found: {source}")
    payload = json.loads(source.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict) or payload.get("version") != 1:
        raise SemanticOracleError("Semantic oracle must be an object with version=1")
    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise SemanticOracleError("Semantic oracle cases must be a non-empty list")
    result: list[SemanticOracleCase] = []
    seen_text: set[str] = set()
    for index, item in enumerate(raw_cases, start=1):
        if not isinstance(item, dict):
            raise SemanticOracleError(f"Oracle case #{index} must be an object")
        text = str(item.get("text", "")).strip()
        if not text:
            raise SemanticOracleError(f"Oracle case #{index} has empty text")
        if text in seen_text:
            raise SemanticOracleError(f"Duplicate oracle text: {text}")
        seen_text.add(text)
        grade = str(item.get("grade", "EXACT")).upper()
        if grade not in {"EXACT", "ARCHITECTURE_GAP"}:
            raise SemanticOracleError(f"Oracle case #{index} has unsupported grade {grade!r}")
        expectation = item.get("expect", {})
        if not isinstance(expectation, dict):
            raise SemanticOracleError(f"Oracle case #{index} expect must be an object")
        note = item.get("note")
        family = str(item.get("family") or "uncategorized").strip() or "uncategorized"
        raw_tags = item.get("tags", [])
        if raw_tags is None:
            raw_tags = []
        if not isinstance(raw_tags, list) or any(not isinstance(tag, str) for tag in raw_tags):
            raise SemanticOracleError(f"Oracle case #{index} tags must be a list of strings")
        tags = tuple(dict.fromkeys(tag.strip() for tag in raw_tags if tag.strip()))
        scenario_id = str(item.get("scenario") or "legacy-sequential").strip() or "legacy-sequential"
        result.append(
            SemanticOracleCase(
                index, text, grade, expectation, str(note) if note else None, family, tags, scenario_id
            )
        )
    return tuple(result)


def validate_oracle_alignment(cases: Sequence[Any], oracle: Sequence[SemanticOracleCase]) -> None:
    case_texts = [str(item.text).strip() for item in cases]
    oracle_texts = [item.text for item in oracle]
    if case_texts != oracle_texts:
        mismatch = next(
            (
                i
                for i, (left, right) in enumerate(zip(case_texts, oracle_texts), start=1)
                if left != right
            ),
            min(len(case_texts), len(oracle_texts)) + 1,
        )
        actual = case_texts[mismatch - 1] if mismatch <= len(case_texts) else "<missing>"
        expected = oracle_texts[mismatch - 1] if mismatch <= len(oracle_texts) else "<missing>"
        raise SemanticOracleError(
            f"Acceptance cases and semantic oracle differ at #{mismatch}: "
            f"cases={actual!r}; oracle={expected!r}"
        )


def _norm(value: Any) -> str:
    text = str(value or "").strip().casefold().replace("ё", "е")
    text = re.sub(r"\s+", " ", text)
    return text


def _check(checks: list[dict[str, Any]], name: str, ok: bool, *, expected: Any = None, actual: Any = None, detail: str | None = None) -> None:
    item: dict[str, Any] = {"name": name, "ok": bool(ok)}
    if expected is not None:
        item["expected"] = expected
    if actual is not None:
        item["actual"] = actual
    if detail:
        item["detail"] = detail
    checks.append(item)


def _decoded_perception(record: Mapping[str, Any]) -> Mapping[str, Any] | None:
    direct = record.get("perception_result")
    if isinstance(direct, dict):
        return direct
    diagnostics = record.get("parser_diagnostics")
    if isinstance(diagnostics, list):
        for item in reversed(diagnostics):
            if isinstance(item, dict) and isinstance(item.get("decoded"), dict):
                return item["decoded"]
    return None


def _predicate_name(item: Mapping[str, Any]) -> str:
    predicate = item.get("predicate")
    if not isinstance(predicate, dict):
        return ""
    return str(predicate.get("normalized_hint") or predicate.get("surface") or "")


def _actant_text(item: Mapping[str, Any]) -> str:
    return str(item.get("normalized_hint") or item.get("mention") or "")


def _role_map(item: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for actant in item.get("actants", []) or []:
        if isinstance(actant, dict):
            result[str(actant.get("role", ""))] = actant
    return result


def _entity_labels(perception: Mapping[str, Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for collection_name in ("assertions", "queries", "commands"):
        for item in perception.get(collection_name, []) or []:
            if not isinstance(item, dict):
                continue
            for actant in item.get("actants", []) or []:
                if not isinstance(actant, dict):
                    continue
                entity_ref = actant.get("entity_ref")
                label = _actant_text(actant)
                if entity_ref and label:
                    labels.setdefault(str(entity_ref), label)
            for alternative in item.get("alternatives", []) or []:
                if not isinstance(alternative, dict):
                    continue
                for actant in alternative.get("actants", []) or []:
                    if not isinstance(actant, dict):
                        continue
                    entity_ref = actant.get("entity_ref")
                    label = _actant_text(actant)
                    if entity_ref and label:
                        labels.setdefault(str(entity_ref), label)
    return labels


def _actual_target_label(actant: Mapping[str, Any], entity_labels: Mapping[str, str]) -> str:
    entity_ref = actant.get("entity_ref")
    if entity_ref and str(entity_ref) in entity_labels:
        return entity_labels[str(entity_ref)]
    return _actant_text(actant)


def _match_composition(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> tuple[bool, Any]:
    composition = actual.get("composition")
    if not isinstance(composition, dict):
        return False, None
    expected_operator = str(expected.get("operator", "")).upper()
    actual_operator = str(composition.get("operator", "")).upper()
    actual_members = [
        str(item.get("normalized_hint") or item.get("mention") or "")
        for item in composition.get("members", []) or []
        if isinstance(item, dict)
    ]
    expected_members = [str(item) for item in expected.get("members", []) or []]
    ok = actual_operator == expected_operator and [_norm(x) for x in actual_members] == [_norm(x) for x in expected_members]
    return ok, {"operator": actual_operator, "members": actual_members}


def _lookup_actual_path(
    path: str,
    expected_key_to_actual: Mapping[str, Mapping[str, Any]],
) -> Mapping[str, Any] | None:
    if "." not in path:
        return None
    key, role = path.split(".", 1)
    assertion = expected_key_to_actual.get(key)
    if assertion is None:
        return None
    return _role_map(assertion).get(role)


def _match_perception_target(
    actual: Mapping[str, Any],
    expected: Mapping[str, Any],
    *,
    entity_labels: Mapping[str, str],
    expected_key_to_actual: Mapping[str, Mapping[str, Any]],
    expected_key_to_local: Mapping[str, str],
) -> tuple[bool, Any]:
    if expected.get("any") is True:
        return True, _actual_target_label(actual, entity_labels)
    if "assertion" in expected:
        wanted = expected_key_to_local.get(str(expected["assertion"]))
        actual_ref = actual.get("candidate_ref")
        return wanted is not None and str(actual_ref or "") == wanted, actual_ref
    if "same_as" in expected:
        other = _lookup_actual_path(str(expected["same_as"]), expected_key_to_actual)
        if other is None:
            return False, None
        left_ref = actual.get("entity_ref") or actual.get("candidate_ref")
        right_ref = other.get("entity_ref") or other.get("candidate_ref")
        if left_ref and right_ref:
            return str(left_ref) == str(right_ref), {"actual_ref": left_ref, "other_ref": right_ref}
        # Canonical identity is checked after Integration. At perception level do
        # not reject a pronoun merely because deterministic entity resolution has
        # not yet assigned a turn-local entity_ref.
        return True, {"deferred_to_canonical": True}
    if "composition" in expected:
        return _match_composition(actual, expected["composition"])
    expected_text = expected.get("text")
    if expected_text is not None:
        actual_text = _actual_target_label(actual, entity_labels)
        return _norm(actual_text) == _norm(expected_text), actual_text
    return True, _actual_target_label(actual, entity_labels)


def _match_assertions(
    checks: list[dict[str, Any]],
    actual_assertions: Sequence[Mapping[str, Any]],
    expected_assertions: Sequence[Mapping[str, Any]],
    entity_labels: Mapping[str, str],
) -> tuple[dict[str, Mapping[str, Any]], dict[str, str]]:
    _check(checks, "perception.assertion_count", len(actual_assertions) == len(expected_assertions), expected=len(expected_assertions), actual=len(actual_assertions))
    expected_key_to_actual: dict[str, Mapping[str, Any]] = {}
    expected_key_to_local: dict[str, str] = {}
    # Establish the expected-key -> actual-local-id map before matching role
    # targets so a parent assertion may point forward to a nested child.
    for position, expected in enumerate(expected_assertions):
        if position >= len(actual_assertions):
            break
        key = str(expected.get("key") or f"a{position + 1}")
        actual = actual_assertions[position]
        expected_key_to_actual[key] = actual
        expected_key_to_local[key] = str(actual.get("local_id", ""))
    for position, expected in enumerate(expected_assertions):
        if position >= len(actual_assertions):
            break
        actual = actual_assertions[position]
        key = str(expected.get("key") or f"a{position + 1}")
        prefix = f"perception.assertions.{key}"
        expected_predicate = str(expected.get("predicate", ""))
        actual_predicate = _predicate_name(actual)
        _check(checks, f"{prefix}.predicate", _norm(actual_predicate) == _norm(expected_predicate), expected=expected_predicate, actual=actual_predicate)
        expected_status = str(expected.get("status", "ASSERTED")).upper()
        actual_status = str(actual.get("status", "ASSERTED")).upper()
        _check(checks, f"{prefix}.status", actual_status == expected_status, expected=expected_status, actual=actual_status)
        expected_negated = bool(expected.get("negated", False))
        actual_negated = bool(actual.get("negated", False))
        _check(checks, f"{prefix}.negated", actual_negated == expected_negated, expected=expected_negated, actual=actual_negated)
        expected_roles = expected.get("roles", {}) or {}
        actual_roles = _role_map(actual)
        _check(checks, f"{prefix}.role_set", set(actual_roles) == set(expected_roles), expected=sorted(expected_roles), actual=sorted(actual_roles))
        for role, target in expected_roles.items():
            if role not in actual_roles:
                continue
            target_spec = target if isinstance(target, dict) else {"text": target}
            ok, actual_target = _match_perception_target(
                actual_roles[role], target_spec,
                entity_labels=entity_labels,
                expected_key_to_actual=expected_key_to_actual,
                expected_key_to_local=expected_key_to_local,
            )
            _check(checks, f"{prefix}.roles.{role}", ok, expected=target_spec, actual=actual_target)

        expected_alternatives = expected.get("alternatives")
        if expected_alternatives is not None:
            actual_alternatives = [item for item in actual.get("alternatives", []) or [] if isinstance(item, dict)]
            _check(checks, f"{prefix}.alternative_count", len(actual_alternatives) == len(expected_alternatives), expected=len(expected_alternatives), actual=len(actual_alternatives))
            for alt_index, alt_expected in enumerate(expected_alternatives):
                if alt_index >= len(actual_alternatives):
                    break
                alt_actual = actual_alternatives[alt_index]
                alt_roles = _role_map(alt_actual)
                for role, target in (alt_expected.get("roles", {}) or {}).items():
                    if role not in alt_roles:
                        _check(checks, f"{prefix}.alternatives.{alt_index + 1}.{role}", False, expected=target, actual="<missing>")
                        continue
                    target_spec = target if isinstance(target, dict) else {"text": target}
                    ok, actual_target = _match_perception_target(
                        alt_roles[role], target_spec,
                        entity_labels=entity_labels,
                        expected_key_to_actual=expected_key_to_actual,
                        expected_key_to_local=expected_key_to_local,
                    )
                    _check(checks, f"{prefix}.alternatives.{alt_index + 1}.{role}", ok, expected=target_spec, actual=actual_target)
    return expected_key_to_actual, expected_key_to_local


def _match_queries(
    checks: list[dict[str, Any]],
    actual_queries: Sequence[Mapping[str, Any]],
    expected_queries: Sequence[Mapping[str, Any]],
    entity_labels: Mapping[str, str],
) -> None:
    _check(checks, "perception.query_count", len(actual_queries) == len(expected_queries), expected=len(expected_queries), actual=len(actual_queries))
    for index, expected in enumerate(expected_queries):
        if index >= len(actual_queries):
            break
        actual = actual_queries[index]
        prefix = f"perception.queries.q{index + 1}"
        expected_predicate = str(expected.get("predicate", ""))
        actual_predicate = _predicate_name(actual)
        _check(checks, f"{prefix}.predicate", _norm(actual_predicate) == _norm(expected_predicate), expected=expected_predicate, actual=actual_predicate)
        expected_mode = str(expected.get("mode", "EXISTS")).upper()
        actual_mode = str(actual.get("query_mode", "EXISTS")).upper()
        _check(checks, f"{prefix}.mode", actual_mode == expected_mode, expected=expected_mode, actual=actual_mode)
        expected_requested_roles = expected.get("requested_roles")
        if expected_requested_roles is None:
            scalar = expected.get("requested_role")
            expected_requested_roles = [] if scalar in (None, "") else [scalar]
        actual_requested_roles = actual.get("requested_roles")
        if actual_requested_roles is None:
            scalar = actual.get("requested_role")
            actual_requested_roles = [] if scalar in (None, "") else [scalar]
        expected_requested_roles = [str(item) for item in expected_requested_roles]
        actual_requested_roles = [str(item) for item in actual_requested_roles]
        _check(
            checks, f"{prefix}.requested_roles",
            actual_requested_roles == expected_requested_roles,
            expected=expected_requested_roles, actual=actual_requested_roles,
        )
        expected_roles = expected.get("roles", {}) or {}
        actual_roles = _role_map(actual)
        _check(checks, f"{prefix}.role_set", set(actual_roles) == set(expected_roles), expected=sorted(expected_roles), actual=sorted(actual_roles))
        for role, target in expected_roles.items():
            if role not in actual_roles:
                continue
            target_spec = target if isinstance(target, dict) else {"text": target}
            ok, actual_target = _match_perception_target(
                actual_roles[role], target_spec,
                entity_labels=entity_labels,
                expected_key_to_actual={},
                expected_key_to_local={},
            )
            _check(checks, f"{prefix}.roles.{role}", ok, expected=target_spec, actual=actual_target)


def _match_relations(
    checks: list[dict[str, Any]],
    actual_relations: Sequence[Mapping[str, Any]],
    expected_relations: Sequence[Mapping[str, Any]],
    key_to_local: Mapping[str, str],
) -> None:
    normalized_actual = [
        (
            str(item.get("relation_id", "")).upper(),
            str(item.get("source_ref", "")),
            str(item.get("target_ref", "")),
        )
        for item in actual_relations
    ]
    normalized_expected = [
        (
            str(item.get("id", "")).upper(),
            key_to_local.get(str(item.get("source", "")), "<missing>"),
            key_to_local.get(str(item.get("target", "")), "<missing>"),
        )
        for item in expected_relations
    ]
    _check(checks, "perception.relations", normalized_actual == normalized_expected, expected=normalized_expected, actual=normalized_actual)


def _match_conditionals(
    checks: list[dict[str, Any]],
    actual_conditionals: Sequence[Mapping[str, Any]],
    expected_conditionals: Sequence[Mapping[str, Any]],
    key_to_local: Mapping[str, str],
) -> None:
    normalized_actual = [
        (
            tuple(str(x) for x in item.get("antecedent_refs", []) or []),
            tuple(str(x) for x in item.get("consequent_refs", []) or []),
        )
        for item in actual_conditionals
    ]
    normalized_expected = [
        (
            tuple(key_to_local.get(str(x), "<missing>") for x in item.get("if", []) or []),
            tuple(key_to_local.get(str(x), "<missing>") for x in item.get("then", []) or []),
        )
        for item in expected_conditionals
    ]
    _check(checks, "perception.conditionals", normalized_actual == normalized_expected, expected=normalized_expected, actual=normalized_actual)


def _snapshot_entity_name(snapshot: Mapping[str, Mapping[str, Any]], uid: str) -> str | None:
    item = snapshot.get(uid)
    if not isinstance(item, dict) or item.get("kind") != "M":
        return None
    prop = (item.get("properties") or {}).get("name")
    if isinstance(prop, dict):
        value = prop.get("value")
        return str(value) if value is not None else None
    return None


def _snapshot_symbol_forms(snapshot: Mapping[str, Mapping[str, Any]], uid: str) -> tuple[str, ...]:
    item = snapshot.get(uid)
    if not isinstance(item, dict) or item.get("kind") != "S":
        return ()
    return tuple(str(value) for value in item.get("forms", []) or [])


def _template_predicate(snapshot: Mapping[str, Mapping[str, Any]], template_uid: str) -> str | None:
    template = snapshot.get(template_uid)
    if not isinstance(template, dict) or template.get("kind") != "T":
        return None
    predicate = template.get("predicate")
    if not isinstance(predicate, dict):
        return None
    forms = _snapshot_symbol_forms(snapshot, str(predicate.get("uid", "")))
    if not forms:
        return None
    # A source-language lemma is normally the shortest reusable form in R_text;
    # oracle comparisons only need membership, so returning the sorted first form
    # is diagnostic display only.
    return sorted(forms, key=lambda x: (len(x), x.casefold()))[0]


def _predicate_matches_template(snapshot: Mapping[str, Mapping[str, Any]], template: Mapping[str, Any], predicate: str) -> bool:
    ref = template.get("predicate")
    if not isinstance(ref, dict):
        return False
    forms = _snapshot_symbol_forms(snapshot, str(ref.get("uid", "")))
    return any(_norm(form) == _norm(predicate) for form in forms)


def _templates_for_predicate(snapshot: Mapping[str, Mapping[str, Any]], predicate: str) -> list[Mapping[str, Any]]:
    return [
        item
        for item in snapshot.values()
        if isinstance(item, dict)
        and item.get("kind") == "T"
        and _predicate_matches_template(snapshot, item, predicate)
    ]


def _resolve_ref_value(snapshot: Mapping[str, Mapping[str, Any]], ref: Mapping[str, Any]) -> Any:
    uid = str(ref.get("uid", ""))
    kind = str(ref.get("kind", ""))
    item = snapshot.get(uid)
    if kind == "M":
        return _snapshot_entity_name(snapshot, uid) or uid
    if kind == "N":
        if not isinstance(item, dict):
            return uid
        template_ref = item.get("template")
        predicate = None
        if isinstance(template_ref, dict):
            predicate = _template_predicate(snapshot, str(template_ref.get("uid", "")))
        return {"kind": "N", "uid": uid, "predicate": predicate}
    if kind == "G" and isinstance(item, dict):
        return {
            "kind": "G",
            "uid": uid,
            "function_id": item.get("function_id"),
            "operands": [_resolve_ref_value(snapshot, operand) for operand in item.get("operands", []) or [] if isinstance(operand, dict)],
        }
    if kind == "K" and isinstance(item, dict):
        return {
            "kind": "K",
            "uid": uid,
            "members": [_resolve_ref_value(snapshot, member) for member in item.get("members", []) or [] if isinstance(member, dict)],
        }
    return uid


def _canonical_target_ref(
    snapshot: Mapping[str, Mapping[str, Any]],
    assertion_ref: Mapping[str, Any],
    role: str,
) -> Mapping[str, Any] | None:
    uid = str(assertion_ref.get("uid", ""))
    kind = str(assertion_ref.get("kind", ""))
    item = snapshot.get(uid)
    if kind == "G" and isinstance(item, dict) and item.get("function_id") == "FALSE":
        operands = item.get("operands", []) or []
        if len(operands) == 1 and isinstance(operands[0], dict):
            return _canonical_target_ref(snapshot, operands[0], role)
    if kind != "N" or not isinstance(item, dict):
        return None
    actants = item.get("actants", {}) or {}
    value = actants.get(role)
    return value if isinstance(value, dict) else None


def _canonical_assertion_predicate_forms(snapshot: Mapping[str, Mapping[str, Any]], assertion_ref: Mapping[str, Any]) -> tuple[str, ...]:
    uid = str(assertion_ref.get("uid", ""))
    kind = str(assertion_ref.get("kind", ""))
    item = snapshot.get(uid)
    if kind == "G" and isinstance(item, dict) and item.get("function_id") in {"FALSE", "OR"}:
        operands = item.get("operands", []) or []
        if operands and isinstance(operands[0], dict):
            return _canonical_assertion_predicate_forms(snapshot, operands[0])
    if kind != "N" or not isinstance(item, dict):
        return ()
    template_ref = item.get("template")
    if not isinstance(template_ref, dict):
        return ()
    template = snapshot.get(str(template_ref.get("uid", "")))
    if not isinstance(template, dict):
        return ()
    predicate_ref = template.get("predicate")
    if not isinstance(predicate_ref, dict):
        return ()
    return _snapshot_symbol_forms(snapshot, str(predicate_ref.get("uid", "")))


def _canonical_role_set(snapshot: Mapping[str, Mapping[str, Any]], assertion_ref: Mapping[str, Any]) -> set[str]:
    uid = str(assertion_ref.get("uid", ""))
    kind = str(assertion_ref.get("kind", ""))
    item = snapshot.get(uid)
    if kind == "G" and isinstance(item, dict) and item.get("function_id") == "FALSE":
        operands = item.get("operands", []) or []
        if len(operands) == 1 and isinstance(operands[0], dict):
            return _canonical_role_set(snapshot, operands[0])
    if kind == "G" and isinstance(item, dict) and item.get("function_id") == "OR":
        operands = item.get("operands", []) or []
        if operands and isinstance(operands[0], dict):
            return _canonical_role_set(snapshot, operands[0])
    if kind != "N" or not isinstance(item, dict):
        return set()
    return set((item.get("actants") or {}).keys())


def _canonical_assertion_ref_map(record: Mapping[str, Any], expected_key_to_local: Mapping[str, str]) -> dict[str, Mapping[str, Any]]:
    commit = record.get("integration_commit")
    if not isinstance(commit, dict):
        return {}
    local_to_ref = {
        str(item.get("local_id", "")): item.get("ref")
        for item in commit.get("assertions", []) or []
        if isinstance(item, dict) and isinstance(item.get("ref"), dict)
    }
    return {
        key: local_to_ref[local]
        for key, local in expected_key_to_local.items()
        if local in local_to_ref
    }


def _canonical_target_matches(
    snapshot: Mapping[str, Mapping[str, Any]],
    actual_ref: Mapping[str, Any] | None,
    expected: Mapping[str, Any],
    *,
    expected_ref_map: Mapping[str, Mapping[str, Any]],
    assertion_expected: Mapping[str, Mapping[str, Any]],
) -> tuple[bool, Any]:
    if actual_ref is None:
        return False, None
    if expected.get("any") is True:
        return True, _resolve_ref_value(snapshot, actual_ref)
    if "assertion" in expected:
        target = expected_ref_map.get(str(expected["assertion"]))
        return target is not None and str(actual_ref.get("uid")) == str(target.get("uid")), _resolve_ref_value(snapshot, actual_ref)
    if "same_as" in expected:
        path = str(expected["same_as"])
        if "." not in path:
            return False, _resolve_ref_value(snapshot, actual_ref)
        key, role = path.split(".", 1)
        other_assertion_ref = expected_ref_map.get(key)
        if other_assertion_ref is None:
            return False, _resolve_ref_value(snapshot, actual_ref)
        other_ref = _canonical_target_ref(snapshot, other_assertion_ref, role)
        return other_ref is not None and str(actual_ref.get("uid")) == str(other_ref.get("uid")), {
            "actual": _resolve_ref_value(snapshot, actual_ref),
            "other": _resolve_ref_value(snapshot, other_ref) if other_ref else None,
        }
    if "composition" in expected:
        uid = str(actual_ref.get("uid", ""))
        item = snapshot.get(uid)
        composition = expected["composition"]
        if not isinstance(item, dict) or item.get("kind") != "G":
            return False, _resolve_ref_value(snapshot, actual_ref)
        expected_operator = str(composition.get("operator", "")).upper()
        if str(item.get("function_id", "")).upper() != expected_operator:
            return False, _resolve_ref_value(snapshot, actual_ref)
        members = [_resolve_ref_value(snapshot, ref) for ref in item.get("operands", []) or [] if isinstance(ref, dict)]
        expected_members = [str(x) for x in composition.get("members", []) or []]
        member_labels = [str(x) if not isinstance(x, dict) else str(x.get("predicate") or x.get("uid")) for x in members]
        return [_norm(x) for x in member_labels] == [_norm(x) for x in expected_members], members
    expected_name = expected.get("canonical_name", expected.get("text"))
    if expected_name is not None:
        value = _resolve_ref_value(snapshot, actual_ref)
        return not isinstance(value, dict) and _norm(value) == _norm(expected_name), value
    return True, _resolve_ref_value(snapshot, actual_ref)


def _match_canonical_assertions(
    checks: list[dict[str, Any]],
    record: Mapping[str, Any],
    snapshot: Mapping[str, Mapping[str, Any]],
    expected_assertions: Sequence[Mapping[str, Any]],
    expected_key_to_local: Mapping[str, str],
) -> dict[str, Mapping[str, Any]]:
    expected_by_key = {str(item.get("key") or f"a{i + 1}"): item for i, item in enumerate(expected_assertions)}
    expected_ref_map = _canonical_assertion_ref_map(record, expected_key_to_local)
    for key, expected in expected_by_key.items():
        expected_status = str(expected.get("status", "ASSERTED")).upper()
        if expected_status == "CONDITIONAL":
            continue
        prefix = f"canonical.assertions.{key}"
        ref = expected_ref_map.get(key)
        _check(checks, f"{prefix}.integrated", ref is not None, expected=True, actual=ref is not None)
        if ref is None:
            continue
        if expected_status == "EMBEDDED":
            scoped_node = _scoped_member_node(snapshot, ref)
            scoped_ok = bool(
                scoped_node is not None
                and scoped_node.get("meta", {}).get("semantic_scope") == "EMBEDDED"
            )
            _check(
                checks, f"{prefix}.scoped", scoped_ok,
                expected="semantic_scope=EMBEDDED", actual=(
                    scoped_node.get("meta", {}).get("semantic_scope")
                    if scoped_node is not None else None
                ),
            )
        predicate_forms = _canonical_assertion_predicate_forms(snapshot, ref)
        expected_predicate = str(expected.get("predicate", ""))
        predicate_ok = any(_norm(form) == _norm(expected_predicate) for form in predicate_forms)
        _check(checks, f"{prefix}.predicate", predicate_ok, expected=expected_predicate, actual=predicate_forms)
        expected_negated = bool(expected.get("negated", False))
        item = snapshot.get(str(ref.get("uid", "")))
        actual_negated = bool(isinstance(item, dict) and item.get("kind") == "G" and item.get("function_id") == "FALSE")
        if any("composition" in (target if isinstance(target, dict) else {}) and str((target if isinstance(target, dict) else {}).get("composition", {}).get("operator", "")).upper() == "OR" for target in (expected.get("roles", {}) or {}).values()):
            # An OR-valued assertion is lifted to g_OR over complete N propositions.
            actual_or = bool(isinstance(item, dict) and item.get("kind") == "G" and item.get("function_id") == "OR")
            _check(checks, f"{prefix}.or_lift", actual_or, expected="G:OR", actual=(item or {}).get("function_id") if isinstance(item, dict) else None)
            continue
        _check(checks, f"{prefix}.negated", actual_negated == expected_negated, expected=expected_negated, actual=actual_negated)
        expected_roles = expected.get("roles", {}) or {}
        actual_roles = _canonical_role_set(snapshot, ref)
        _check(checks, f"{prefix}.role_set", actual_roles == set(expected_roles), expected=sorted(expected_roles), actual=sorted(actual_roles))
        for role, target in expected_roles.items():
            target_spec = target if isinstance(target, dict) else {"text": target}
            actual_target_ref = _canonical_target_ref(snapshot, ref, role)
            ok, actual_value = _canonical_target_matches(
                snapshot,
                actual_target_ref,
                target_spec,
                expected_ref_map=expected_ref_map,
                assertion_expected=expected_by_key,
            )
            _check(checks, f"{prefix}.roles.{role}", ok, expected=target_spec, actual=actual_value)
    return expected_ref_map


def _scoped_member_node(
    snapshot: Mapping[str, Mapping[str, Any]], ref: Mapping[str, Any]
) -> Mapping[str, Any] | None:
    item = snapshot.get(str(ref.get("uid", "")))
    if not isinstance(item, dict):
        return None
    if item.get("kind") == "G" and str(item.get("function_id", "")).upper() in {"FALSE", "NOT"}:
        operands = item.get("operands", []) or []
        if len(operands) != 1 or not isinstance(operands[0], dict):
            return None
        item = snapshot.get(str(operands[0].get("uid", "")))
    return item if isinstance(item, dict) and item.get("kind") == "N" else None


def _match_integrated_conditionals(
    checks: list[dict[str, Any]],
    snapshot: Mapping[str, Mapping[str, Any]],
    commit: Mapping[str, Any],
    expected_conditionals: Sequence[Mapping[str, Any]],
) -> None:
    actual = [item for item in commit.get("conditionals", []) or [] if isinstance(item, dict)]
    _check(
        checks,
        "integration.conditional_count",
        len(actual) == len(expected_conditionals),
        expected=len(expected_conditionals),
        actual=len(actual),
    )
    for index, expected in enumerate(expected_conditionals):
        if index >= len(actual):
            break
        item = actual[index]
        prefix = f"integration.conditionals.c{index + 1}"
        top_ref = item.get("ref")
        antecedent_ref = item.get("antecedent")
        consequent_ref = item.get("consequent")
        top = snapshot.get(str(top_ref.get("uid", ""))) if isinstance(top_ref, dict) else None
        top_ok = bool(
            isinstance(top, dict)
            and top.get("kind") == "G"
            and str(top.get("function_id", "")).upper() == "IF"
            and top.get("operands") == [antecedent_ref, consequent_ref]
        )
        _check(
            checks, f"{prefix}.if_function", top_ok,
            expected="IF(antecedent, consequent)",
            actual=(top or {}).get("function_id") if isinstance(top, dict) else None,
        )

        expected_if = [str(x) for x in expected.get("if", []) or []]
        expected_then = [str(x) for x in expected.get("then", []) or []]
        members = [ref for ref in item.get("member_refs", []) or [] if isinstance(ref, dict)]
        expected_member_count = len(expected_if) + len(expected_then)
        _check(
            checks, f"{prefix}.member_count", len(members) == expected_member_count,
            expected=expected_member_count, actual=len(members),
        )

        def match_side(name: str, side_ref: Any, expected_predicates: list[str], member_slice: list[Mapping[str, Any]]) -> None:
            if not isinstance(side_ref, dict):
                _check(checks, f"{prefix}.{name}.shape", False, expected="canonical ref", actual=side_ref)
                return
            side = snapshot.get(str(side_ref.get("uid", "")))
            if len(expected_predicates) == 1:
                shape_ok = not (
                    isinstance(side, dict)
                    and side.get("kind") == "G"
                    and str(side.get("function_id", "")).upper() == "AND"
                ) and bool(member_slice) and side_ref == member_slice[0]
                expected_shape = "SINGLE"
                actual_shape = (side or {}).get("function_id", "SINGLE") if isinstance(side, dict) else None
            else:
                shape_ok = bool(
                    isinstance(side, dict)
                    and side.get("kind") == "G"
                    and str(side.get("function_id", "")).upper() == "AND"
                    and side.get("operands") == member_slice
                )
                expected_shape = "AND"
                actual_shape = (side or {}).get("function_id") if isinstance(side, dict) else None
            _check(
                checks, f"{prefix}.{name}.shape", shape_ok,
                expected=expected_shape, actual=actual_shape,
            )

            actual_predicates: list[Any] = []
            predicate_matches: list[bool] = []
            all_scoped = True
            for position, ref in enumerate(member_slice):
                node = _scoped_member_node(snapshot, ref)
                expected_name = expected_predicates[position] if position < len(expected_predicates) else ""
                if node is None:
                    all_scoped = False
                    actual_predicates.append("<missing>")
                    predicate_matches.append(False)
                    continue
                all_scoped = all_scoped and node.get("meta", {}).get("semantic_scope") == "CONDITIONAL"
                forms = _canonical_assertion_predicate_forms(snapshot, ref)
                actual_predicates.append(forms)
                predicate_matches.append(any(_norm(form) == _norm(expected_name) for form in forms))
            predicates_ok = (
                len(member_slice) == len(expected_predicates)
                and len(predicate_matches) == len(expected_predicates)
                and all(predicate_matches)
            )
            _check(
                checks, f"{prefix}.{name}.predicates", predicates_ok,
                expected=expected_predicates, actual=actual_predicates,
            )
            _check(
                checks, f"{prefix}.{name}.scoped", all_scoped,
                expected="semantic_scope=CONDITIONAL", actual=all_scoped,
            )

        split = len(expected_if)
        match_side("antecedent", antecedent_ref, expected_if, members[:split])
        match_side("consequent", consequent_ref, expected_then, members[split:split + len(expected_then)])


def _clarification_options(snapshot: Mapping[str, Mapping[str, Any]], commit: Mapping[str, Any]) -> tuple[str, ...]:
    labels: list[str] = []
    for clarification in commit.get("clarifications", []) or []:
        if not isinstance(clarification, dict):
            continue
        for option in clarification.get("options", []) or []:
            if not isinstance(option, dict):
                continue
            label = option.get("label")
            if label:
                labels.append(str(label))
            elif isinstance(option.get("ref"), dict):
                labels.append(str(_resolve_ref_value(snapshot, option["ref"])))
    return tuple(labels)


def _match_integration(
    checks: list[dict[str, Any]],
    record: Mapping[str, Any],
    snapshot: Mapping[str, Mapping[str, Any]],
    integration_expectation: Mapping[str, Any],
    expected_assertions: Sequence[Mapping[str, Any]],
    expected_key_to_local: Mapping[str, str],
) -> None:
    runtime_ok = str(record.get("status", "ERROR")) == "OK"
    must_succeed = bool(integration_expectation.get("must_succeed", True))
    _check(checks, "integration.completed", runtime_ok == must_succeed, expected="OK" if must_succeed else "ERROR", actual=record.get("status"))
    if not runtime_ok:
        safe_error = integration_expectation.get("safe_error_contains")
        if safe_error:
            actual_error = str(record.get("error", ""))
            _check(checks, "integration.safe_error", str(safe_error) in actual_error, expected=safe_error, actual=actual_error)
        return

    commit = record.get("integration_commit")
    if not isinstance(commit, dict):
        _check(checks, "integration.commit_present", False, expected=True, actual=False)
        return
    _check(checks, "integration.commit_present", True, expected=True, actual=True)
    expected_world_count = integration_expectation.get("world_assertion_count")
    if expected_world_count is not None:
        actual_count = len(commit.get("assertions", []) or [])
        _check(checks, "integration.world_assertion_count", actual_count == int(expected_world_count), expected=int(expected_world_count), actual=actual_count)

    expected_cp_additions = integration_expectation.get("cp_semantic_addition_count")
    if expected_cp_additions is not None:
        added = (record.get("ah_diff", {}) or {}).get("added", {}) or {}

        def ref_domain(ref: Any) -> str | None:
            if not isinstance(ref, dict):
                return None
            uid = ref.get("uid")
            if uid is None:
                return None
            target = snapshot.get(str(uid))
            if not isinstance(target, dict):
                return None
            domain = target.get("domain")
            return str(domain) if domain is not None else None

        # H experiences use canonical T wrappers even though the experiences
        # themselves live in H.  In a scenario-isolated acceptance run that
        # infrastructure T may be created on the first turn of every scenario.
        # It is not a C/P interpretation of the user's sentence and therefore
        # must not make a safe H-only clarification look like a world-semantic
        # write.  Detect these wrappers structurally rather than by predicate
        # spelling: an added T is H infrastructure when an added H event_instance
        # N points to it as its template.
        h_experience_template_uids = {
            str((item.get("template") or {}).get("uid"))
            for item in added.values()
            if isinstance(item, dict)
            and item.get("kind") == "N"
            and item.get("domain") == "H"
            and bool((item.get("meta") or {}).get("event_instance"))
            and isinstance(item.get("template"), dict)
            and (item.get("template") or {}).get("uid")
        }

        def is_cp_semantic_addition(uid: str, item: Mapping[str, Any]) -> bool:
            if item.get("kind") == "T" and uid in h_experience_template_uids:
                return False
            if item.get("domain") in {"C", "P"}:
                return True
            if item.get("kind") != "L":
                return False
            # Links are domainless canonical objects. Count them as C/P semantic
            # additions only when they actually touch C/P semantics. H→H FOLLOW
            # links belong to experience chronology and must not make a safe
            # structural-clarification turn look like a world-semantic write.
            return any(
                ref_domain(item.get(endpoint)) in {"C", "P"}
                for endpoint in ("source", "target")
            )

        semantic_added = [
            uid for uid, item in added.items()
            if isinstance(item, dict) and is_cp_semantic_addition(str(uid), item)
        ]
        _check(
            checks, "integration.cp_semantic_addition_count",
            len(semantic_added) == int(expected_cp_additions),
            expected=int(expected_cp_additions), actual=semantic_added,
        )

    expected_conditionals = integration_expectation.get("conditionals")
    if isinstance(expected_conditionals, list):
        _match_integrated_conditionals(checks, snapshot, commit, expected_conditionals)

    clarification = integration_expectation.get("clarification")
    if isinstance(clarification, dict):
        expected_required = bool(clarification.get("required", False))
        actual_required = bool(commit.get("clarification_required", False))
        _check(checks, "integration.clarification.required", actual_required == expected_required, expected=expected_required, actual=actual_required)
        if expected_required:
            expected_kind = clarification.get("kind")
            if expected_kind is not None:
                actual_kinds = tuple(
                    str(item.get("kind", ""))
                    for item in commit.get("clarifications", []) or []
                    if isinstance(item, dict)
                )
                _check(
                    checks, "integration.clarification.kind",
                    actual_kinds == (str(expected_kind),),
                    expected=(str(expected_kind),), actual=actual_kinds,
                )
            expected_options = tuple(str(x) for x in clarification.get("options", []) or [])
            actual_options = _clarification_options(snapshot, commit)
            _check(
                checks,
                "integration.clarification.options",
                sorted(_norm(x) for x in actual_options) == sorted(_norm(x) for x in expected_options),
                expected=expected_options,
                actual=actual_options,
            )
            if "pending_armed" in clarification:
                expected_pending = bool(clarification.get("pending_armed"))
                context_after = record.get("interaction_context_after", {}) or {}
                pending = context_after.get("pending_clarification_refs", []) or []
                actual_pending = bool(pending)
                _check(
                    checks, "integration.clarification.pending_armed",
                    actual_pending == expected_pending,
                    expected=expected_pending, actual=pending,
                )

    expected_domains = integration_expectation.get("domains", {}) or {}
    local_to_domain = {
        str(item.get("local_id", "")): str(item.get("domain", ""))
        for item in commit.get("assertions", []) or []
        if isinstance(item, dict)
    }
    for key, expected_domain in expected_domains.items():
        local = expected_key_to_local.get(str(key))
        actual_domain = local_to_domain.get(str(local), "<missing>")
        _check(checks, f"integration.domains.{key}", actual_domain == str(expected_domain), expected=expected_domain, actual=actual_domain)

    expected_query_outcomes = integration_expectation.get("query_outcomes", []) or []
    actual_query_outcomes = record.get("queries", []) or []
    _check(checks, "inference.query_outcome_count", len(actual_query_outcomes) == len(expected_query_outcomes), expected=len(expected_query_outcomes), actual=len(actual_query_outcomes))
    for index, expected in enumerate(expected_query_outcomes):
        if index >= len(actual_query_outcomes):
            break
        item = actual_query_outcomes[index]
        raw_outcome = item.get("outcome") if isinstance(item, dict) else None
        outcome = raw_outcome if isinstance(raw_outcome, dict) else {}
        expected_status = str(expected.get("status", "PROVED"))
        actual_status = str(outcome.get("status", ""))
        _check(checks, f"inference.q{index + 1}.status", actual_status == expected_status, expected=expected_status, actual=actual_status)
        expected_role = expected.get("role")
        conclusion = outcome.get("conclusion") if isinstance(outcome, dict) else None
        actual_role = conclusion.get("role") if isinstance(conclusion, dict) else None
        if expected_role is not None:
            _check(checks, f"inference.q{index + 1}.role", str(actual_role or "") == str(expected_role), expected=expected_role, actual=actual_role)
        expected_value = expected.get("value")
        if expected_value is not None:
            value_ref = conclusion.get("value") if isinstance(conclusion, dict) else None
            actual_value = _resolve_ref_value(snapshot, value_ref) if isinstance(value_ref, dict) else None
            _check(checks, f"inference.q{index + 1}.value", not isinstance(actual_value, dict) and _norm(actual_value) == _norm(expected_value), expected=expected_value, actual=actual_value)
        expected_bindings = expected.get("bindings")
        if isinstance(expected_bindings, dict):
            actual_bindings_raw = conclusion.get("bindings", []) if isinstance(conclusion, dict) else []
            actual_bindings: dict[str, Any] = {}
            for pair in actual_bindings_raw or []:
                if not isinstance(pair, (list, tuple)) or len(pair) != 2:
                    continue
                role, value_ref = pair
                actual_bindings[str(role)] = (
                    _resolve_ref_value(snapshot, value_ref) if isinstance(value_ref, dict) else None
                )
            _check(
                checks, f"inference.q{index + 1}.binding_roles",
                set(actual_bindings) == set(str(role) for role in expected_bindings),
                expected=sorted(str(role) for role in expected_bindings),
                actual=sorted(actual_bindings),
            )
            for role, expected_binding in expected_bindings.items():
                actual_binding = actual_bindings.get(str(role))
                _check(
                    checks, f"inference.q{index + 1}.bindings.{role}",
                    not isinstance(actual_binding, dict) and _norm(actual_binding) == _norm(expected_binding),
                    expected=expected_binding, actual=actual_binding,
                )


def _update_required_template_roles(
    requirements: MutableMapping[str, set[str]],
    expected_assertions: Sequence[Mapping[str, Any]],
    expected_queries: Sequence[Mapping[str, Any]],
) -> None:
    for item in expected_assertions:
        if str(item.get("status", "ASSERTED")).upper() not in {"ASSERTED", "EMBEDDED", "CONDITIONAL"}:
            continue
        predicate = str(item.get("predicate", ""))
        if not predicate:
            continue
        requirements.setdefault(predicate, set()).update(str(role) for role in (item.get("roles", {}) or {}))
    for item in expected_queries:
        predicate = str(item.get("predicate", ""))
        if not predicate:
            continue
        roles = requirements.setdefault(predicate, set())
        roles.update(str(role) for role in (item.get("roles", {}) or {}))
        requested_many = item.get("requested_roles")
        if requested_many is not None:
            roles.update(str(requested) for requested in requested_many)
        else:
            requested = item.get("requested_role")
            if requested:
                roles.add(str(requested))


def _check_template_coverage(
    checks: list[dict[str, Any]],
    snapshot: Mapping[str, Mapping[str, Any]],
    requirements: Mapping[str, set[str]],
    predicates_touched: Iterable[str],
) -> None:
    for predicate in sorted(set(predicates_touched), key=_norm):
        required = requirements.get(predicate, set())
        if not required:
            continue
        templates = _templates_for_predicate(snapshot, predicate)
        role_sets = [set(str(role) for role in item.get("roles", []) or []) for item in templates]
        covered = any(required.issubset(roles) for roles in role_sets)
        _check(
            checks,
            f"templates.{predicate}.explicit_role_coverage",
            covered,
            expected=sorted(required),
            actual=[sorted(roles) for roles in role_sets],
            detail="Canonical T must cover every role explicitly observed or requested so far; hidden roles are not required by this check.",
        )


def evaluate_semantic_case(
    record: Mapping[str, Any],
    oracle_case: SemanticOracleCase,
    after_snapshot: Mapping[str, Mapping[str, Any]],
    required_template_roles: MutableMapping[str, set[str]],
) -> SemanticCaseVerdict:
    checks: list[dict[str, Any]] = []
    expected = oracle_case.expectation
    perception_expectation = expected.get("perception", {}) or {}
    expected_assertions = perception_expectation.get("assertions", []) or []
    expected_queries = perception_expectation.get("queries", []) or []

    actual_perception = _decoded_perception(record)
    must_parse = bool(perception_expectation.get("must_parse", True))
    _check(checks, "perception.available", (actual_perception is not None) == must_parse, expected=must_parse, actual=actual_perception is not None)

    key_to_actual: dict[str, Mapping[str, Any]] = {}
    key_to_local: dict[str, str] = {}
    if actual_perception is not None:
        entity_labels = _entity_labels(actual_perception)
        actual_assertions = [item for item in actual_perception.get("assertions", []) or [] if isinstance(item, dict)]
        actual_queries = [item for item in actual_perception.get("queries", []) or [] if isinstance(item, dict)]
        key_to_actual, key_to_local = _match_assertions(checks, actual_assertions, expected_assertions, entity_labels)
        _match_queries(checks, actual_queries, expected_queries, entity_labels)
        _match_relations(
            checks,
            [item for item in actual_perception.get("relations", []) or [] if isinstance(item, dict)],
            perception_expectation.get("relations", []) or [],
            key_to_local,
        )
        _match_conditionals(
            checks,
            [item for item in actual_perception.get("conditionals", []) or [] if isinstance(item, dict)],
            perception_expectation.get("conditionals", []) or [],
            key_to_local,
        )

    _update_required_template_roles(required_template_roles, expected_assertions, expected_queries)
    integration_expectation = expected.get("integration", {}) or {}
    _match_integration(checks, record, after_snapshot, integration_expectation, expected_assertions, key_to_local)

    if str(record.get("status", "ERROR")) == "OK" and key_to_local:
        _match_canonical_assertions(checks, record, after_snapshot, expected_assertions, key_to_local)

    touched_predicates = [str(item.get("predicate", "")) for item in expected_assertions]
    touched_predicates.extend(str(item.get("predicate", "")) for item in expected_queries)
    if oracle_case.grade == "EXACT" and str(record.get("status", "ERROR")) == "OK":
        _check_template_coverage(checks, after_snapshot, required_template_roles, touched_predicates)

    has_failures = any(not item.get("ok", False) for item in checks)
    if has_failures:
        status = "FAIL"
    elif oracle_case.grade == "ARCHITECTURE_GAP":
        status = "GAP"
    else:
        status = "PASS"
    return SemanticCaseVerdict(
        oracle_case.index, oracle_case.text, status, tuple(checks), oracle_case.note,
        oracle_case.family, oracle_case.tags,
    )


def summarize_semantic_verdicts(verdicts: Sequence[SemanticCaseVerdict]) -> SemanticOracleReport:
    family_counts: dict[str, dict[str, int]] = {}
    for item in verdicts:
        bucket = family_counts.setdefault(item.family, {"total": 0, "passed": 0, "failed": 0, "gaps": 0})
        bucket["total"] += 1
        if item.status == "PASS":
            bucket["passed"] += 1
        elif item.status == "FAIL":
            bucket["failed"] += 1
        elif item.status == "GAP":
            bucket["gaps"] += 1
    return SemanticOracleReport(
        total=len(verdicts),
        passed=sum(item.status == "PASS" for item in verdicts),
        failed=sum(item.status == "FAIL" for item in verdicts),
        gaps=sum(item.status == "GAP" for item in verdicts),
        cases=tuple(verdicts),
        family_counts=family_counts,
    )


def apply_ah_diff(snapshot: MutableMapping[str, dict[str, Any]], diff: Mapping[str, Any]) -> None:
    for uid in (diff.get("removed", {}) or {}):
        snapshot.pop(str(uid), None)
    for uid, payload in (diff.get("changed", {}) or {}).items():
        if isinstance(payload, dict) and isinstance(payload.get("after"), dict):
            snapshot[str(uid)] = dict(payload["after"])
    for uid, payload in (diff.get("added", {}) or {}).items():
        if isinstance(payload, dict):
            snapshot[str(uid)] = dict(payload)


def evaluate_acceptance_bundle(
    run_dir: str | Path,
    oracle_file: str | Path,
    *,
    write_report: bool = True,
) -> SemanticOracleReport:
    root = Path(run_dir)
    oracle = load_semantic_oracle(oracle_file)
    initial_path = root / "initial_ah.json"
    if not initial_path.is_file():
        raise FileNotFoundError(f"Acceptance bundle has no initial_ah.json: {root}")
    initial_snapshot: dict[str, dict[str, Any]] = json.loads(initial_path.read_text(encoding="utf-8"))
    snapshot: dict[str, dict[str, Any]] = deepcopy(initial_snapshot)
    required_template_roles: dict[str, set[str]] = {}
    verdicts: list[SemanticCaseVerdict] = []
    active_scenario: str | None = None
    for case in oracle:
        if active_scenario != case.scenario_id:
            snapshot = deepcopy(initial_snapshot)
            required_template_roles = {}
            active_scenario = case.scenario_id
        turn_path = root / f"turn_{case.index:03d}.json"
        if not turn_path.is_file():
            raise FileNotFoundError(f"Acceptance bundle missing {turn_path.name}")
        record = json.loads(turn_path.read_text(encoding="utf-8"))
        if str(record.get("input", "")).strip() != case.text:
            raise SemanticOracleError(
                f"Bundle/oracle text mismatch at #{case.index}: "
                f"bundle={record.get('input')!r}; oracle={case.text!r}"
            )
        apply_ah_diff(snapshot, record.get("ah_diff", {}) or {})
        verdicts.append(evaluate_semantic_case(record, case, snapshot, required_template_roles))

    report = summarize_semantic_verdicts(verdicts)
    if write_report:
        payload = {
            "total": report.total,
            "passed": report.passed,
            "failed": report.failed,
            "gaps": report.gaps,
            "families": report.family_counts,
            "cases": [
                {
                    "index": item.index,
                    "text": item.text,
                    "status": item.status,
                    "note": item.note,
                    "family": item.family,
                    "tags": list(item.tags),
                    "checks": list(item.checks),
                }
                for item in report.cases
            ],
        }
        (root / "semantic_report.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        lines = [
            f"Semantic oracle: PASS {report.passed}/{report.total} | FAIL {report.failed} | GAP {report.gaps}",
            "",
            "Families:",
        ]
        for family, counts in report.family_counts.items():
            lines.append(
                f"  {family}: PASS {counts['passed']}/{counts['total']} | "
                f"FAIL {counts['failed']} | GAP {counts['gaps']}"
            )
        lines.append("")
        for item in report.cases:
            line = f"{item.index:03d} {item.status}: {item.text}"
            if item.failures:
                failed_names = ", ".join(check["name"] for check in item.failures[:6])
                if len(item.failures) > 6:
                    failed_names += f", ... (+{len(item.failures) - 6})"
                line += f" | {failed_names}"
            if item.note and item.status == "GAP":
                line += f" | {item.note}"
            lines.append(line)
        (root / "semantic_summary.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return report
