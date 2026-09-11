from __future__ import annotations

import json
from pathlib import Path

import pytest

from ah.core import AHCore
from ah.core.persistence import JsonPersistence, PersistenceError
from ah.config import PersistenceSettings
from ah.logic import FunctionRegistry
from ah.model import BoundVar, Domain, RefKind, VariableSort


def _proposition(core: AHCore):
    s = core.add_abstract_symbol({"работать"}, uid="S_WORK")
    t = core.add_template(Domain.C, core.ref(s.uid), (), uid="T_WORK")
    n, _ = core.add_hypernode(Domain.C, core.ref(t.uid), {}, 0.5, uid="N_WORK")
    return core.ref(n.uid)


def test_registry_has_v4_logical_kernel_and_legacy_if_alias() -> None:
    registry = FunctionRegistry()
    assert registry.canonical_id("AND") == "AND"
    assert registry.canonical_id("if") == "IMPLIES"
    assert registry.get("IMPLIES").reasoner_handler == "IMPLIES"
    assert registry.get("POSSIBLE").reasoner_handler == "POSSIBLE"
    assert registry.get("REQUIRED").reasoner_handler == "REQUIRED"
    assert registry.get("PERMITTED").reasoner_handler == "PERMITTED"
    assert registry.get("FORALL").reasoner_handler == "FORALL"
    assert registry.get("EXISTS").reasoner_handler == "EXISTS"


def test_core_rejects_unregistered_g_id() -> None:
    core = AHCore()
    proposition = _proposition(core)
    with pytest.raises(KeyError):
        core.add_function(Domain.C, "MAGIC_LOGIC", (proposition,))


def test_core_rejects_invalid_registered_arity() -> None:
    core = AHCore()
    proposition = _proposition(core)
    with pytest.raises(ValueError):
        core.add_function(Domain.C, "AND", (proposition,))


def test_quantifier_contract_is_boundvar_plus_formula_ref() -> None:
    core = AHCore()
    proposition = _proposition(core)
    variable = BoundVar(0, VariableSort.ENTITY)
    g = core.add_function(Domain.C, "EXISTS", (variable, proposition), uid="G_EXISTS")
    assert g.operands == (variable, proposition)
    with pytest.raises(ValueError):
        core.add_function(Domain.C, "EXISTS", (proposition, proposition))


def test_legacy_if_is_accepted_but_registry_reports_implies_semantics() -> None:
    core = AHCore()
    proposition = _proposition(core)
    g = core.add_function(Domain.C, "IF", (proposition, proposition), uid="G_IF")
    assert g.function_id == "IF"
    assert core.function_registry.canonical_id(g.function_id) == "IMPLIES"


def test_persistence_rejects_unknown_function_id(tmp_path: Path) -> None:
    core = AHCore()
    proposition = _proposition(core)
    core.add_function(Domain.C, "NOT", (proposition,), uid="G_NOT")
    path = tmp_path / "ah.json"
    persistence = JsonPersistence(path, PersistenceSettings())
    persistence.save(core)
    raw = json.loads(path.read_text(encoding="utf-8"))
    for item in raw["canonical"]["elements"]:
        if item.get("uid") == "G_NOT":
            item["function_id"] = "UNKNOWN_FUNCTION"
    path.write_text(json.dumps(raw, ensure_ascii=False), encoding="utf-8")
    with pytest.raises(PersistenceError):
        persistence.load()


def test_legacy_declaration_only_quantifier_can_be_rendered_for_diagnostics() -> None:
    registry = FunctionRegistry()
    assert registry.render("FORALL", ("$0:ENTITY",)) == "FORALL $0:ENTITY: <UNRESOLVED_BODY>"
    assert registry.render("EXISTS", ("$0:ENTITY",)) == "EXISTS $0:ENTITY: <UNRESOLVED_BODY>"



def test_modal_wrappers_require_one_proposition_operand() -> None:
    core = AHCore()
    proposition = _proposition(core)
    possible = core.add_function(Domain.C, "POSSIBLE", (proposition,))
    assert possible.function_id == "POSSIBLE"
    with pytest.raises(ValueError):
        core.add_function(Domain.C, "POSSIBLE", (proposition, proposition))



def test_modal_function_roundtrips_through_persistence(tmp_path: Path) -> None:
    core = AHCore()
    proposition = _proposition(core)
    modal = core.add_function(
        Domain.C, "REQUIRED", (proposition,), uid="G_REQUIRED"
    )
    path = tmp_path / "modal.json"
    persistence = JsonPersistence(path, PersistenceSettings())
    persistence.save(core)

    loaded = persistence.load().core
    restored = loaded.store.get_element_any_domain(modal.uid)
    assert restored.function_id == "REQUIRED"
    assert restored.operands == (proposition,)
    assert loaded.function_registry.render(
        "REQUIRED", ("server works",)
    ) == "REQUIRED (server works)"
