"""Independent TEST_ONLY finite-clause grammar, compiled from released valencies.

This is resource data construction, not a new production parser or a set of
sentence exceptions. The existing SyntaxRules interpreter evaluates each rule,
retains whole dictionary alternatives and passes candidates through T3/T4.
Only complete one-token finite predicates and one-token ENTITY arguments are
covered. Scope, quotation, prepositions, multiword mentions and other material
remain uncovered and require the ordinary bounded proposal mechanism.
"""
from __future__ import annotations

from copy import deepcopy
from itertools import combinations

from ah.formalizer.canonical_ledger import digest


def _junction(op, args):
    return args[0] if len(args) == 1 else {"op": op, "args": args}


def _complete_window(captures):
    """Every token is captured or terminal punctuation; no opaque alignment.

    OVERLAPS compares source ranges, independent of a variant's missing POS.
    Thus punctuation with POS=None does not introduce an UNKNOWN guard and an
    uncaptured content word cannot disappear merely because it lacks a parse.
    """
    covered = [{"op": "span_relation", "left": "item", "right": name,
                "relation": "OVERLAPS"} for name in captures]
    covered.append({"op": "feature_in", "field": "item.surface",
                    "values": [".", "!", "?"]})
    return {"op": "NOT", "arg": {"op": "window_has", "source": "TOKEN",
        "expr": {"op": "NOT", "arg": _junction("OR", covered)}}}


def finite_clause_rules(resources, *, max_arguments=3):
    """Build generic role/case patterns from R-S/R-V, without oracle inputs.

    Resource sense IDs license a grammar shape but are never model choices or
    canonical node IDs. No lemma, surface sentence, case ID, ranking score or
    expected conclusion is hardcoded. Optional ENTITY arguments enumerate all
    declared retained subsets. Non-ENTITY, plural-cardinality and preposition
    dependencies are deliberately outside this small exact-coverage grammar.
    A missing/unsupported shape produces no rule; it does not gain a fallback
    valency or an invented argument.

    The caller must pin R-S and R-V in SyntaxRules.dependency_versions and sign
    the resulting TEST_ONLY release. Production loading never calls this helper.
    """
    if type(max_arguments) is not int or not 0 <= max_arguments <= 3:
        raise ValueError("finite fixture grammar supports at most three arguments")
    finite = {sense["sense_id"]: sense for sense in resources["R-S"]
              if sense["POS"] == "VERB" and not sense.get("anchor_pattern")}
    registry = {row["role_id"] for row in resources["RoleRegistry"]}
    shapes = {}
    for valency in resources["R-V"]:
        sid = valency["sense_id"]
        if sid not in finite:
            continue
        roles = sorted(valency.get("roles", ()), key=lambda role: role["role_id"])
        # A single captured token cannot stand for multiple entities or a
        # proposition. In particular, a quoted CONTENT slot is never dropped.
        if any(role["role_id"] not in registry
               or set(role.get("argument_types", ())) != {"ENTITY"}
               or role.get("allowed_preps")
               or not role.get("allowed_cases")
               or role.get("cardinality", {}).get("max") != 1
               for role in roles):
            continue
        required = [role for role in roles if role.get("cardinality", {}).get("min", 0) > 0]
        optional = [role for role in roles if role not in required]
        for count in range(len(optional) + 1):
            for retained in combinations(optional, count):
                selected = sorted([*required, *retained], key=lambda role: role["role_id"])
                if len(selected) > max_arguments:
                    continue
                signature = tuple((role["role_id"], tuple(sorted(set(role["allowed_cases"]))))
                                  for role in selected)
                shapes.setdefault(signature, set()).add(sid)
    rules = []
    for signature, sense_ids in sorted(shapes.items()):
        # This is a lossless resource-derived search prefilter, not a chosen
        # reading: every matching whole VERB parse remains an independent join.
        # Without it, unrelated complex clauses exhaust the bounded joins for
        # a valency shape their own released predicate cannot ever license.
        captures = {"p": {"all": [{"POS": ["VERB"]},
            {"lemma": sorted({finite[sid]["lemma"] for sid in sense_ids})}]}}
        nodes = [{"id": "p", "kind": "PREDICATE", "anchors": ["p"]}]
        edges = []
        for index, (role_id, cases) in enumerate(signature):
            # The existing interpreter walks capture names in sorted order.
            # Put the resource-licensed predicate first so unrelated sentences
            # do not enumerate argument-only joins before finding no predicate.
            name = "r" + str(index)
            captures[name] = {"POS": ["NOUN", "NPRO"], "cases": list(cases)}
            nodes.append({"id": name, "kind": "ENTITY", "anchors": [name]})
            edges.append({"kind": "ARGUMENT", "from": "p", "to": name,
                          "role_id": role_id})
        # The capture's lemma set was derived only from R-S senses admitting
        # this exact R-V shape. One declared lookup proves the finite reading
        # exists; enumerating every sense lookup again adds no information and
        # needlessly spends the bounded join budget. Distinct shapes remain
        # distinct rules, and T3 still checks each actual R-S/R-V sense.
        known = {"op": "schema_lookup", "resource": "R-S", "key": {
                    "lemma": {"field": "p.lemma"}, "POS": {"field": "p.POS"}}}
        rules.append({"rule_id": "TEST_ONLY:FINITE:" + digest(signature),
            "input_feature_pattern": {"captures": captures, "window": "SENTENCE",
                "where": {"op": "AND", "args": [_complete_window(captures),
                            known]}},
            "output_kind": "CANDIDATE_GRAPH", "output": {"nodes": nodes, "edges": edges},
            "constraints": [], "priority": 0, "min_evidence": len(captures),
            "coverage_tag": "TEST_ONLY:COMPLETE_FINITE_ENTITY_CLAUSE"})
    return deepcopy(rules)
