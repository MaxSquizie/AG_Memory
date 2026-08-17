from __future__ import annotations

import json
from pathlib import Path
import unittest

from ah.config import LLMRoleSettings
from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
from ah.perception.contracts import ActantRole
from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
from ah.perception.morphology import MorphInfo
from legacy_semantic_fixture import legacy_semantic_answer


PROJECT = Path(__file__).resolve().parents[1]


class FocusedMorphology:
    name = "broad200-regression"
    DATA = {
        "анна": MorphInfo("Анна", "NOUN", case="nomn", gender="femn", number="sing", score=1.0),
        "петра": MorphInfo("Пётр", "NOUN", case="accs", gender="masc", number="sing", score=1.0),
        "книгу": MorphInfo("книга", "NOUN", case="accs", gender="femn", number="sing", score=1.0),
        "хочет": MorphInfo("хотеть", "VERB", number="sing", score=1.0),
        "попросить": MorphInfo("попросить", "INFN", score=1.0),
        "прийти": MorphInfo("прийти", "INFN", score=1.0),
        "купить": MorphInfo("купить", "INFN", score=1.0),
        "прочитать": MorphInfo("прочитать", "INFN", score=1.0),
        "и": MorphInfo("и", "CONJ", score=1.0),
        "вода": MorphInfo("вода", "NOUN", case="nomn", gender="femn", number="sing", score=1.0),
        "осталась": MorphInfo("остаться", "VERB", gender="femn", number="sing", score=1.0),
        "холодной": MorphInfo("холодный", "ADJF", case="ablt", gender="femn", number="sing", score=1.0),
        "иван": MorphInfo("Иван", "NOUN", case="nomn", gender="masc", number="sing", score=1.0),
        "марии": MorphInfo("Мария", "NOUN", case="datv", gender="femn", number="sing", score=1.0),
        "что": MorphInfo("что", "NPRO", case="accs", score=1.0),
        "читает": MorphInfo("читать", "VERB", number="sing", score=1.0),
        "подарил": MorphInfo("подарить", "VERB", gender="masc", number="sing", score=1.0),
        "сергей": MorphInfo("Сергей", "NOUN", case="nomn", gender="masc", number="sing", score=1.0),
        "папку": MorphInfo("папка", "NOUN", case="accs", gender="femn", number="sing", score=1.0),
        "положил": MorphInfo("положить", "VERB", gender="masc", number="sing", score=1.0),
        "на": MorphInfo("на", "PREP", score=1.0),
        "полку": MorphInfo("полка", "NOUN", case="accs", gender="femn", number="sing", score=1.0),
    }

    def analyze(self, word: str):
        return self.DATA.get(word.casefold())

    def analyze_all(self, word: str):
        item = self.analyze(word)
        return () if item is None else (item,)


class NoLLMBackend:
    def generate(self, prompt, *, system="", override=None, role="generic"):
        raise AssertionError(f"unexpected semantic probe {role}:\n{prompt}")


class FixtureBackend:
    def __init__(self, answers=None):
        self.answers = {key: list(values) for key, values in (answers or {}).items()}
        self.roles = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.roles.append(role)
        values = self.answers.get(role)
        if values:
            answer = values.pop(0)
        else:
            answer = legacy_semantic_answer(role, prompt)
        if answer is None:
            raise AssertionError(f"unexpected semantic probe {role}:\n{prompt}")
        from ah.llm import LLMResponse
        return LLMResponse(str(answer), {})


class Broad200Regression20260817Tests(unittest.TestCase):
    def test_nonfinite_chain_uses_intermediate_nonfinite_governor(self):
        graph = LinguisticCandidateBuilder(FocusedMorphology()).build(
            "Анна хочет попросить Петра прийти."
        )
        dependencies = {
            (edge.parent_token_index, edge.child_token_index)
            for edge in graph.frame_graph.dependencies
        }
        self.assertEqual(dependencies, {(2, 3), (3, 5)})

    def test_coordinated_nonfinites_remain_siblings(self):
        graph = LinguisticCandidateBuilder(FocusedMorphology()).build(
            "Анна хочет купить и прочитать книгу."
        )
        dependencies = {
            (edge.parent_token_index, edge.child_token_index)
            for edge in graph.frame_graph.dependencies
        }
        self.assertEqual(dependencies, {(2, 3), (2, 5)})
        self.assertEqual(
            [group.member_token_indices for group in graph.frame_graph.coordinations],
            [(3, 5)],
        )

    def test_proven_adjectival_copular_state_entails_holder_subject(self):
        parser = AdaptivePerceptionParser(
            NoLLMBackend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=FocusedMorphology(),
        )
        result = parser.parse("Вода осталась холодной.").perception
        assertion = result.assertions[0]
        self.assertEqual(
            {(item.role, item.mention) for item in assertion.actants},
            {(ActantRole.SUBJECT, "Вода"), (ActantRole.STATE, "холодной")},
        )

    def test_acceptance_oracle_embeds_proposition_valued_children(self):
        data = json.loads((PROJECT / "data/acceptance_oracle.json").read_text(encoding="utf-8"))
        checked = 0
        for case in data["cases"]:
            assertions = case.get("expect", {}).get("perception", {}).get("assertions", [])
            by_key = {item.get("key"): item for item in assertions}
            for parent in assertions:
                for role, target in (parent.get("roles", {}) or {}).items():
                    if role not in {"OBJECT", "PURPOSE", "HOW-TO", "HOW_TO"}:
                        continue
                    if not isinstance(target, dict) or "assertion" not in target:
                        continue
                    child = by_key[target["assertion"]]
                    if child.get("status") == "CONDITIONAL":
                        continue
                    checked += 1
                    self.assertEqual(child.get("status"), "EMBEDDED", case["text"])
        self.assertGreater(checked, 10)

    def test_actant_candidates_are_enumerated_without_llm_stop_vote(self):
        backend = FixtureBackend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=FocusedMorphology(),
        )
        assertion = parser.parse("Иван читает книгу.").perception.assertions[0]
        self.assertEqual(
            {(item.role, item.normalized_hint) for item in assertion.actants},
            {(ActantRole.SUBJECT, "Иван"), (ActantRole.OBJECT, "книга")},
        )
        self.assertNotIn("perception_actant_start", backend.roles)

    def test_query_resolves_overt_actants_before_wh_gap_role(self):
        backend = FixtureBackend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=FocusedMorphology(),
        )
        query = parser.parse("Что Иван подарил Марии?").perception.queries[0]
        self.assertEqual(query.requested_role, ActantRole.OBJECT)
        self.assertEqual(
            {(item.role, item.normalized_hint) for item in query.actants},
            {(ActantRole.SUBJECT, "Иван"), (ActantRole.RECIPIENT, "Мария")},
        )

    def test_unambiguous_pp_attachment_is_resolved_before_clarification(self):
        backend = FixtureBackend({
            "perception_modifier_attachment": ["EVENT"],
            "perception_role_cue": [
                "ACTOR_OR_EXPERIENCER",
                "AFFECTED_OR_CONTENT",
                "PLACE",
            ],
        })
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=FocusedMorphology(),
        )
        assertion = parser.parse("Сергей положил папку на полку.").perception.assertions[0]
        roles = {item.role: item.normalized_hint for item in assertion.actants}
        self.assertEqual(roles[ActantRole.SUBJECT], "Сергей")
        self.assertEqual(roles[ActantRole.OBJECT], "папка")
        self.assertEqual(roles[ActantRole.LOCATION], "полка")
        self.assertIn("perception_modifier_attachment", backend.roles)

    def test_probe_prompts_encode_runtime_failures_found_by_broad200(self):
        role_prompt = (PROJECT / "prompts/perception/role_cue.txt").read_text(encoding="utf-8")
        self.assertIn("does not change TARGET's role", role_prompt)
        for name in ("predicate_start", "predicate_end", "actant_start", "actant_end"):
            text = (PROJECT / "prompts/perception" / f"{name}.txt").read_text(encoding="utf-8")
            self.assertIn("integer option number", text)
            self.assertIn("without brackets", text)


if __name__ == "__main__":
    unittest.main()
