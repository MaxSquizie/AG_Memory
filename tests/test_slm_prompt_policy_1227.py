from pathlib import Path
import re
import unittest

PROJECT = Path(__file__).resolve().parents[1]


class SLMPromptPolicy1227Tests(unittest.TestCase):
    def test_service_prompt_files_contain_no_cyrillic_instructions(self):
        offenders = []
        for path in (PROJECT / "prompts").rglob("*.txt"):
            if re.search(r"[А-Яа-яЁё]", path.read_text(encoding="utf-8")):
                offenders.append(str(path.relative_to(PROJECT)))
        self.assertEqual(offenders, [])

    def test_template_hidden_valency_uses_binary_generation_protocol(self):
        text = (PROJECT / "prompts/perception" / "template_hidden_valency.txt").read_text(encoding="utf-8")
        self.assertIn("Choose exactly one label from CHOICES", text)
        self.assertIn("Known roles", text)
        self.assertNotIn("RECIPIENT,SOURCE", text)
        self.assertNotIn("AMBIGUOUS", text)
        self.assertNotIn("likelihood", text.casefold())
        self.assertFalse((PROJECT / "prompts/perception" / "template_candidate_system.txt").exists())
        self.assertFalse((PROJECT / "prompts/perception" / "template_event_semantics.txt").exists())
        self.assertFalse((PROJECT / "prompts/perception" / "semantic_completion_system.txt").exists())


    def test_semantic_probes_use_small_contrastive_or_direct_choices_without_abstention_labels(self):
        for name in (
            "frame_relation.txt", "control_subject.txt",
            "role_family.txt", "role_participant.txt", "role_description.txt",
            "role_circumstance.txt",
        ):
            text = (PROJECT / "prompts/perception" / name).read_text(encoding="utf-8")
            self.assertIn("Choose exactly one label", text, name)
            self.assertNotIn("YES or NO", text, name)
            self.assertNotIn("UNKNOWN", text, name)
            self.assertNotIn("NONE", text, name)

    def test_retired_template_guessing_prompts_are_absent(self):
        retired = (
            "template_subject_slot.txt", "template_direct_object.txt",
            "template_event_direction.txt", "template_event_directionality.txt",
            "template_event_frame.txt", "template_hidden_role.txt",
            "template_more_core.txt", "template_role.txt",
            "template_role_family.txt", "template_schema.txt",
        )
        for name in retired:
            self.assertFalse((PROJECT / "prompts/perception" / name).exists(), name)



if __name__ == "__main__":
    unittest.main()
