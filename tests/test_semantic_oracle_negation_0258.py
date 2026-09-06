from ah.diagnostics.semantic_oracle import (
    _canonical_assertion_predicate_forms,
    _canonical_role_set,
    _canonical_target_ref,
)


def _snapshot():
    return {
        "S_buy": {"uid": "S_buy", "kind": "S", "forms": ["купить", "купил"]},
        "T_buy": {"uid": "T_buy", "kind": "T", "predicate": {"uid": "S_buy", "kind": "S"}},
        "M_maria": {"uid": "M_maria", "kind": "M", "properties": {"name": {"value": "Мария"}}},
        "M_book": {"uid": "M_book", "kind": "M", "properties": {"name": {"value": "книга"}}},
        "N_buy": {
            "uid": "N_buy", "kind": "N", "template": {"uid": "T_buy", "kind": "T"},
            "actants": {
                "SUBJECT": {"uid": "M_maria", "kind": "M"},
                "OBJECT": {"uid": "M_book", "kind": "M"},
            },
        },
        "G_not": {"uid": "G_not", "kind": "G", "function_id": "NOT", "operands": [{"uid": "N_buy", "kind": "N"}]},
    }


def test_canonical_oracle_unwraps_object_level_not_for_predicate_and_roles():
    snapshot = _snapshot()
    ref = {"uid": "G_not", "kind": "G"}
    assert "купить" in _canonical_assertion_predicate_forms(snapshot, ref)
    assert _canonical_role_set(snapshot, ref) == {"SUBJECT", "OBJECT"}
    assert _canonical_target_ref(snapshot, ref, "SUBJECT") == {"uid": "M_maria", "kind": "M"}
