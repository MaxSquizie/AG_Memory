from __future__ import annotations

from legacy_semantic_fixture import legacy_semantic_answer

from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from contextlib import nullcontext
from types import SimpleNamespace

from ah.agent.interaction_context import InteractionContext
from ah.agent.llm_agent import LLMAgent, LLMAgentSettings
from ah.bootstrap import RuntimeServices
from ah.config import LLMRoleSettings, load_config
from ah.llm import LLMResponse
from ah.perception import LLMPerceptionService, LLMPerceptionSettings, PerceptionParseError
from ah.model import ActantRole, Domain
from ah.core import AHCore, SequentialUidGenerator
from ah.perception import PredicateCandidate, TextSensoryService
from ah.integration.template_resolver import TemplateResolver
from ah.llm.worker import _resolve_loader_type, _resolve_device_map, _generation_config_values, _score_fixed_choices, _score_fixed_choice_details, generate as worker_generate
from ah.projection.contracts import AgentContext


PROJECT = Path(__file__).resolve().parents[1]


class CaptureBackend:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, prompt, *, system="", override=None, role="generic"):
        self.calls.append((role, prompt, system, dict(override or {})))
        if role == "perception":
            return LLMResponse('{"assertions":[],"queries":[],"commands":[],"diagnostics":[]}', {})
        return LLMResponse("ответ", {})


class LLMRoleTests(unittest.TestCase):
    def test_worker_fixed_choice_scoring_returns_only_allowed_option(self) -> None:
        import torch

        class Tokenizer:
            def __call__(self, text, *, return_tensors="pt", add_special_tokens=False):
                ids = {"0": [1], "1": [2]}[text]
                return {"input_ids": torch.tensor([ids], dtype=torch.long)}

        class Model:
            device = "cpu"
            def __call__(self, *, input_ids, attention_mask, use_cache=False):
                logits = torch.zeros((1, input_ids.shape[-1], 8), dtype=torch.float32)
                # Candidate likelihood is read from the position before its token.
                logits[:, 1, 1] = 1.0
                logits[:, 1, 2] = 5.0
                return SimpleNamespace(logits=logits)

        runtime = {
            "torch": torch,
            "tokenizer": Tokenizer(),
            "model": Model(),
            "input_device": "cpu",
        }
        inputs = {
            "input_ids": torch.tensor([[5, 6]], dtype=torch.long),
            "attention_mask": torch.tensor([[1, 1]], dtype=torch.long),
        }
        self.assertEqual(_score_fixed_choices(runtime, inputs, ["0", "1"]), "1")
        details = _score_fixed_choice_details(runtime, inputs, ["0", "1"])
        self.assertEqual(details["choice"], "1")
        self.assertGreater(details["choice_margin"], 0.0)
        self.assertEqual(set(details["choice_scores"]), {"0", "1"})

    def test_same_backend_can_serve_stateless_perception_and_agent_roles(self) -> None:
        with TemporaryDirectory() as td:
            root = Path(td)
            perception_prompt = root / "perception.txt"
            agent_prompt = root / "agent.txt"
            perception_prompt.write_text("PARSER_PROMPT", encoding="utf-8")
            agent_prompt.write_text("AGENT_PROMPT", encoding="utf-8")
            backend = CaptureBackend()
            parser = LLMPerceptionService(
                backend,
                LLMPerceptionSettings(
                    system_prompt_path=perception_prompt,
                    generation=LLMRoleSettings(128, 0.0, 1.0, 0),
                    protocol="legacy_json",
                    probe_retry_attempts=0,
                ),
            )
            agent = LLMAgent(
                backend,
                LLMAgentSettings(
                    agent_prompt,
                    LLMRoleSettings(64, 0.2, 0.9, 40),
                ),
            )
            parsed = parser.parse("Иван спит", InteractionContext())
            answer = agent.respond(AgentContext("x", (), (), "# CURRENT INPUT\nx"))
            self.assertEqual(parsed.source_text, "Иван спит")
            self.assertEqual(answer, "ответ")
            self.assertEqual([call[0] for call in backend.calls], ["perception", "agent"])
            self.assertEqual(backend.calls[0][2], "PARSER_PROMPT")
            self.assertEqual(backend.calls[1][2], "AGENT_PROMPT")
            self.assertEqual(backend.calls[0][3]["temperature"], 0.0)
            self.assertEqual(backend.calls[1][3]["temperature"], 0.2)


    def test_agent_passes_configured_context_budget_to_backend(self) -> None:
        backend = CaptureBackend()
        agent = LLMAgent(backend, LLMAgentSettings(context_max_tokens=321))
        agent.respond(AgentContext("x", (), (), "# CURRENT INPUT\nx"))
        self.assertEqual(backend.calls[-1][3]["max_input_tokens"], 321)

    def test_compact_perception_protocol_expands_into_runtime_contracts(self) -> None:
        backend = CaptureBackend()
        parser = LLMPerceptionService(backend, LLMPerceptionSettings())
        result = parser.parse_response(
            "Иван сказал, что Мария спит",
            '{"a":[{"id":"A1","p":"спит","n":"спать","neg":false,"r":[["SUBJECT","Мария"]]},'
            '{"id":"A2","p":"сказал","n":"сказать","neg":false,"r":[["SUBJECT","Иван"],["OBJECT","@A1"]]}],"q":[],"c":[]}',
        )
        self.assertEqual(len(result.assertions), 2)
        self.assertEqual(result.assertions[0].predicate.lookup_form, "спать")
        self.assertEqual(result.assertions[1].actants[1].role, ActantRole.OBJECT)
        self.assertEqual(result.assertions[1].actants[1].candidate_ref, "A1")
        self.assertIsNone(result.assertions[0].actants[0].parser_confidence)
        self.assertIsNone(result.assertions[0].actants[0].evidence)
        string_false = parser.parse_response(
            "Мария спит",
            '{"a":[{"id":"A1","p":"спит","neg":"false","r":[["SUBJECT","Мария"]]}],"q":[],"c":[]}',
        )
        self.assertFalse(string_false.assertions[0].negated)

    def test_invalid_parser_json_gets_one_stateless_repair_attempt(self) -> None:
        class RepairBackend:
            def __init__(self):
                self.roles = []

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception":
                    return LLMResponse("not json", {})
                return LLMResponse('{"a":[],"q":[],"c":[]}', {})

        backend = RepairBackend()
        parser = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(protocol="legacy_json", repair_attempts=1),
        )
        result = parser.parse("привет", InteractionContext())
        self.assertEqual(result.acts_count, 0)
        self.assertEqual(backend.roles, ["perception", "perception_repair"])

    def test_default_adaptive_probe_prompts_stay_tiny_and_worker_auto_is_text_only(self) -> None:
        probe_dir = PROJECT / "prompts/perception"
        for path in probe_dir.glob("*.txt"):
            self.assertLess(len(path.read_text(encoding="utf-8")), 360, path.name)
        self.assertEqual(_resolve_loader_type(PROJECT, "auto"), "causal_lm")
        cfg = load_config(PROJECT / "config/default.toml")
        self.assertEqual(cfg.llm.loader_type, "causal_lm")
        self.assertEqual(cfg.llm.perception_protocol, "adaptive_v3")
        self.assertEqual(cfg.llm.perception_probe_retry_attempts, 1)
        self.assertEqual(cfg.llm.perception_predicate_symbol_language, "en")


    def test_parser_diagnostics_capture_raw_repair_and_decoded_result(self) -> None:
        class RepairBackend:
            def __init__(self):
                self.calls = 0

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.calls += 1
                if self.calls == 1:
                    return LLMResponse("broken", {})
                return LLMResponse('{"a":[],"q":[],"c":[]}', {})

        parser = LLMPerceptionService(
            RepairBackend(),
            LLMPerceptionSettings(protocol="legacy_json", repair_attempts=1),
        )
        result = parser.parse("тест", InteractionContext())
        self.assertEqual(result.acts_count, 0)
        history = parser.diagnostics()
        self.assertEqual(len(history), 1)
        diag = history[-1]
        self.assertEqual(diag.source_text, "тест")
        self.assertEqual([a.role for a in diag.attempts], ["perception", "perception_repair"])
        self.assertIsNotNone(diag.attempts[0].error)
        self.assertIsNone(diag.attempts[1].error)
        self.assertIsNotNone(diag.decoded)
        self.assertIsNone(diag.final_error)

    def test_adaptive_parser_uses_english_semantic_labels_and_numeric_token_choices(self) -> None:
        class ScriptedBackend:
            def __init__(self):
                self.calls = []
                self.answers = {
                    "perception_act_type": ["ASSERTION", "NONE"],
                    "perception_predicate_start": ["2"],
                    "perception_predicate_end": ["2"],
                    "perception_predicate_symbol": ["be"],
                    "perception_actant_start": ["1", "1"],
                    "perception_role_cue": ["ACTOR_OR_EXPERIENCER", "PREDICATED_STATE"],
                }

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.calls.append((role, prompt, system, dict(override or {})))
                return LLMResponse(self.answers[role].pop(0), {})

        backend = ScriptedBackend()
        parser = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(
                protocol="adaptive_v2",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
            ),
        )
        result = parser.parse("Яблоки бывают красные", InteractionContext())
        self.assertEqual(len(result.assertions), 1)
        assertion = result.assertions[0]
        self.assertEqual(assertion.predicate.surface, "бывают")
        self.assertEqual(assertion.predicate.lookup_form, "be")
        self.assertFalse(assertion.negated)
        self.assertEqual([(a.role, a.mention) for a in assertion.actants], [
            (ActantRole.SUBJECT, "Яблоки"),
            (ActantRole.STATE, "красные"),
        ])
        self.assertTrue(all(call[0].startswith("perception_") for call in backend.calls))
        self.assertTrue(all(len(call[2]) < 360 for call in backend.calls))
        self.assertTrue(all(call[3]["max_new_tokens"] <= 10 for call in backend.calls))
        for role, prompt, _system, override in backend.calls:
            if "OPTIONS:" in prompt or "CHOICES:" in prompt:
                self.assertNotIn("choice_outputs", override, role)
        self.assertNotIn("perception_negation", [call[0] for call in backend.calls])
        diag = parser.diagnostics()[-1]
        self.assertTrue(all(a.prompt for a in diag.attempts))
        self.assertEqual(diag.attempts[0].normalized_answer, "ASSERTION")
        self.assertTrue(any(a.raw_text == "<deterministic>" for a in diag.attempts))

    def test_adaptive_query_fill_role_is_built_from_numeric_choices(self) -> None:
        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["0"],
                    "perception_predicate_start": ["2"],
                    "perception_predicate_end": ["2"],
                    "perception_predicate_symbol": ["love"],
                    "perception_query_mode": ["2"],
                    "perception_role_cue": ["AFFECTED_OR_CONTENT", "ACTOR_OR_EXPERIENCER"],
                    "perception_actant_start": ["1"],
                }
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse(self.answers[role].pop(0), {})

        parser = LLMPerceptionService(
            Backend(),
            LLMPerceptionSettings(protocol="adaptive_v2", probe_prompt_dir=PROJECT / "prompts/perception", probe_retry_attempts=0),
        )
        result = parser.parse("Кто любит чай?", InteractionContext())
        self.assertEqual(len(result.queries), 1)
        query = result.queries[0]
        self.assertEqual(query.predicate.lookup_form, "love")
        self.assertEqual(query.requested_role, ActantRole.SUBJECT)
        self.assertEqual(query.query_mode.value, "FILL_ROLE")
        self.assertEqual([(a.role, a.mention) for a in query.actants], [(ActantRole.OBJECT, "чай")])
        self.assertIsNone(query.predicate.template_candidate)

    def test_adaptive_command_uses_same_discrete_span_and_role_pipeline(self) -> None:
        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["3", "0"],
                    "perception_predicate_start": ["1"],
                    "perception_predicate_end": ["1"],
                    "perception_predicate_symbol": ["open"],
                    "perception_actant_start": ["1"],
                    "perception_role_cue": ["AFFECTED_OR_CONTENT"],
                }
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse(self.answers[role].pop(0), {})

        parser = LLMPerceptionService(
            Backend(),
            LLMPerceptionSettings(protocol="adaptive_v2", probe_prompt_dir=PROJECT / "prompts/perception", probe_retry_attempts=0),
        )
        result = parser.parse("Открой дверь", InteractionContext())
        self.assertEqual(len(result.commands), 1)
        command = result.commands[0]
        self.assertEqual(command.predicate.lookup_form, "open")
        self.assertEqual([(a.role, a.mention) for a in command.actants], [(ActantRole.OBJECT, "дверь")])

    def test_adaptive_numeric_probes_accept_terminal_punctuation_only(self) -> None:
        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["1.", "0."],
                    "perception_predicate_start": ["2."],
                    "perception_predicate_end": ["2."],
                    "perception_predicate_symbol": ["be."],
                    "perception_actant_start": ["1.", "1."],
                    # Binary semantic protocol is exact and intentionally does
                    # not accept punctuation. This test keeps punctuation only on
                    # the numeric/open-text probes it is meant to exercise.
                    "perception_role_cue": ["ACTOR_OR_EXPERIENCER", "PREDICATED_STATE"],
                }

            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse(self.answers[role].pop(0), {})

        parser = LLMPerceptionService(
            Backend(),
            LLMPerceptionSettings(
                protocol="adaptive_v2",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
            ),
        )
        result = parser.parse("Яблоки бывают красные", InteractionContext())
        self.assertEqual(len(result.assertions), 1)
        assertion = result.assertions[0]
        self.assertEqual(assertion.predicate.lookup_form, "be")
        self.assertEqual([(a.role, a.mention) for a in assertion.actants], [
            (ActantRole.SUBJECT, "Яблоки"),
            (ActantRole.STATE, "красные"),
        ])


    def test_adaptive_numeric_normalization_accepts_weak_model_format_only_echo(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser

        self.assertEqual(AdaptivePerceptionParser._integer("1 ="), 1)
        self.assertEqual(AdaptivePerceptionParser._integer("[1]"), 1)
        self.assertEqual(AdaptivePerceptionParser._integer("(1):"), 1)
        with self.assertRaises(Exception):
            AdaptivePerceptionParser._integer("1 = claim")
        with self.assertRaises(Exception):
            AdaptivePerceptionParser._integer("I choose 1")

    def test_adaptive_numeric_normalization_does_not_extract_choice_from_prose(self) -> None:
        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse("I choose 1.", {})

        parser = LLMPerceptionService(
            Backend(),
            LLMPerceptionSettings(
                protocol="adaptive_v2",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
            ),
        )
        with self.assertRaises(PerceptionParseError):
            parser.parse("Яблоки бывают красные", InteractionContext())
        self.assertIn("expected one integer option number", parser.diagnostics()[-1].final_error or "")

    def test_adaptive_probe_retry_is_clean_and_never_receives_previous_bad_answer(self) -> None:
        class RetryBackend:
            def __init__(self):
                self.calls = []
                self.act_type_calls = 0

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.calls.append((role, prompt, system))
                if role == "perception_act_type":
                    self.act_type_calls += 1
                    if self.act_type_calls == 1:
                        return LLMResponse("I choose 1", {})
                    return LLMResponse("NONE", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = RetryBackend()
        parser = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(
                protocol="adaptive_v2",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=1,
            ),
        )
        result = parser.parse("привет", InteractionContext())
        self.assertEqual(result.acts_count, 0)
        self.assertEqual(len(backend.calls), 2)
        self.assertEqual(backend.calls[0][1], backend.calls[1][1])
        self.assertNotIn("I choose 1", backend.calls[1][1])
        diag = parser.diagnostics()[-1]
        self.assertIsNotNone(diag.attempts[0].error)
        self.assertEqual(diag.attempts[1].normalized_answer, "NONE")

    def test_adaptive_v3_prompts_are_self_contained_and_have_no_examples(self) -> None:
        probe_dir = PROJECT / "prompts/perception"
        joined = "\n".join(path.read_text(encoding="utf-8") for path in probe_dir.glob("*.txt"))
        for unexplained in ("N-M", "ActantRole", "UID", "hypernode", "AH memory"):
            self.assertNotIn(unexplained, joined)
        for anchor in ("for example", "e.g.", "example", "например"):
            self.assertNotIn(anchor, joined.casefold())
        self.assertIn("without brackets", (probe_dir / "predicate_start.txt").read_text(encoding="utf-8"))
        self.assertIn("Choose exactly one label", (probe_dir / "role_family.txt").read_text(encoding="utf-8"))

    def test_template_predicate_s_reuses_source_lexeme_and_registers_surface_form(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        lexical_s = core.add_abstract_symbol({"бывать"})

        from ah.perception import TemplateCandidate
        resolved = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(
                surface="бывают",
                normalized_hint="бывать",
                template_candidate=TemplateCandidate((ActantRole.SUBJECT, ActantRole.STATE)),
            ),
            (ActantRole.SUBJECT, ActantRole.STATE),
        )
        predicate_s = core.store.get_symbol(resolved.template.predicate.uid)
        self.assertEqual(predicate_s.uid, lexical_s.uid)
        self.assertEqual(predicate_s.forms, frozenset({"бывать", "бывают"}))

    def test_adaptive_act_type_probe_puts_plain_options_before_task_and_does_not_show_tokens(self) -> None:
        class Backend:
            def __init__(self):
                self.call = None
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.call = (prompt, system, role)
                return LLMResponse("0", {})

        backend = Backend()
        parser = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(
                protocol="adaptive_v2",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
            ),
        )
        parser.parse("Яблоки бывают зелёные", InteractionContext())
        prompt, system, role = backend.call
        self.assertEqual(role, "perception_act_type")
        self.assertIn("TEXT:\nЯблоки бывают зелёные", prompt)
        self.assertNotIn("TOKENS:", prompt)
        self.assertIn("OPTIONS:\nNONE: none or unclear", prompt)
        self.assertIn("ASSERTION: states information as a claim/fact", prompt)
        self.assertIn("\n\nTASK:\n", prompt)
        self.assertTrue(prompt.rstrip().endswith("Return only the label."))
        self.assertNotIn("example", prompt.casefold())
        self.assertIn("Do not copy", system)

    def test_worker_chat_template_is_tokenized_once_without_duplicate_special_tokens(self) -> None:
        from ah.llm.worker import _encode_prompt

        class FakeTensor:
            shape = (1, 3)
        class DirectTokenizer:
            def __init__(self):
                self.called = None
            def apply_chat_template(self, messages, **kwargs):
                self.called = kwargs
                return {"input_ids": FakeTensor()}

        tok = DirectTokenizer()
        encoded = _encode_prompt({"tokenizer": tok, "enable_thinking": False}, "sys", "user")
        self.assertIn("input_ids", encoded)
        self.assertTrue(tok.called["tokenize"])
        self.assertTrue(tok.called["add_generation_prompt"])
        self.assertEqual(tok.called["return_tensors"], "pt")
        self.assertTrue(tok.called["return_dict"])

        class FallbackTokenizer:
            def __init__(self):
                self.add_special_tokens = None
            def apply_chat_template(self, messages, tokenize=False, add_generation_prompt=True, **kwargs):
                if tokenize:
                    raise TypeError("old tokenizer")
                return "rendered-chat"
            def __call__(self, prompt, *, return_tensors, add_special_tokens):
                self.add_special_tokens = add_special_tokens
                return {"input_ids": FakeTensor()}

        fallback = FallbackTokenizer()
        _encode_prompt({"tokenizer": fallback, "enable_thinking": False}, "sys", "user")
        self.assertFalse(fallback.add_special_tokens)

    def test_worker_encode_prompt_honors_request_local_thinking_override(self) -> None:
        from ah.llm.worker import _encode_prompt

        class FakeTensor:
            shape = (1, 3)

        class Tokenizer:
            def __init__(self):
                self.thinking = None

            def apply_chat_template(self, messages, **kwargs):
                self.thinking = kwargs.get("enable_thinking")
                return {"input_ids": FakeTensor()}

        tok = Tokenizer()
        _encode_prompt(
            {"tokenizer": tok, "enable_thinking": False},
            "sys",
            "user",
            enable_thinking=True,
        )
        self.assertTrue(tok.thinking)

    def test_worker_refuses_to_silently_truncate_overflowing_context(self) -> None:
        class FakeTensor:
            shape = (1, 100)

        class FakeTokenizer:
            def apply_chat_template(
                self, messages, tokenize=False, add_generation_prompt=True,
                return_tensors=None, return_dict=False, **kwargs
            ):
                if tokenize:
                    return {"input_ids": FakeTensor()}
                return "prompt"

        runtime = {
            "tokenizer": FakeTokenizer(),
            "model": object(),
            "ctx_total": 128,
            "enable_thinking": False,
        }
        defaults = SimpleNamespace(
            max_new_tokens=64, temperature=0.0, top_p=1.0, top_k=0,
            repetition_penalty=1.0, no_repeat_ngram_size=0,
        )
        with self.assertRaisesRegex(ValueError, "Refusing to silently truncate AgentContext"):
            worker_generate(runtime, {"system": "s", "prompt": "u", "override": {}}, defaults)

    def test_worker_passes_generation_settings_only_via_generation_config(self) -> None:
        class FakeTensor:
            shape = (1, 3)

            def to(self, _device):
                return self

            def __getitem__(self, _item):
                return self

        class FakeOutput:
            def __getitem__(self, _item):
                return "generated"

        class FakeTokenizer:
            pad_token_id = 0
            eos_token_id = 2

            def __call__(self, _prompt, return_tensors="pt", add_special_tokens=True):
                raise AssertionError("direct chat-template tokenization should be used")

            def decode(self, _tokens, skip_special_tokens=True):
                return "ok"

            def apply_chat_template(
                self, messages, tokenize=False, add_generation_prompt=True,
                return_tensors=None, return_dict=False, **kwargs
            ):
                if tokenize:
                    self.last_messages = messages
                    return {"input_ids": FakeTensor(), "attention_mask": FakeTensor()}
                return "prompt"

        class FakeGenerationConfig:
            def __init__(self, **kwargs):
                self.__dict__.update(kwargs)

        class FakeModel:
            device = "cpu"

            def __init__(self):
                self.kwargs = None

            def generate(self, **kwargs):
                self.kwargs = kwargs
                return FakeOutput()

        model = FakeModel()
        runtime = {
            "tokenizer": FakeTokenizer(),
            "model": model,
            "ctx_total": 1024,
            "torch": SimpleNamespace(inference_mode=lambda: nullcontext()),
            "enable_thinking": False,
            "strip_thinking": False,
            "GenerationConfig": FakeGenerationConfig,
            "input_device": "cpu",
        }
        defaults = SimpleNamespace(
            max_new_tokens=64, temperature=0.0, top_p=1.0, top_k=0,
            repetition_penalty=1.05, no_repeat_ngram_size=0,
        )
        text = worker_generate(runtime, {"system": "s", "prompt": "u", "override": {}}, defaults)
        self.assertEqual(text, "ok")
        self.assertIn("generation_config", model.kwargs)
        for forbidden in (
            "max_new_tokens", "do_sample", "temperature", "top_p", "top_k",
            "repetition_penalty", "pad_token_id", "eos_token_id",
        ):
            self.assertNotIn(forbidden, model.kwargs)
        gc = model.kwargs["generation_config"]
        self.assertEqual(gc.max_new_tokens, 64)
        self.assertFalse(gc.do_sample)
        self.assertFalse(hasattr(gc, "temperature"))
        self.assertFalse(hasattr(gc, "top_p"))
        self.assertFalse(hasattr(gc, "top_k"))

    def test_generation_config_omits_sampling_flags_for_greedy_parser(self) -> None:
        greedy = _generation_config_values(
            max_new=64, temperature=0.0, top_p=0.7, top_k=3,
            repetition_penalty=1.0, no_repeat_ngram_size=0,
            pad_token_id=0, eos_token_id=2, bos_token_id=1,
        )
        self.assertFalse(greedy["do_sample"])
        self.assertNotIn("temperature", greedy)
        self.assertNotIn("top_p", greedy)
        self.assertNotIn("top_k", greedy)
        self.assertTrue(greedy["use_cache"])
        no_cache = _generation_config_values(
            max_new=1, temperature=0.0, top_p=1.0, top_k=0,
            repetition_penalty=1.0, no_repeat_ngram_size=0, use_cache=False,
            pad_token_id=0, eos_token_id=2, bos_token_id=1,
        )
        self.assertFalse(no_cache["use_cache"])

        sampled = _generation_config_values(
            max_new=64, temperature=0.2, top_p=0.9, top_k=40,
            repetition_penalty=1.0, no_repeat_ngram_size=0,
            pad_token_id=0, eos_token_id=2, bos_token_id=1,
        )
        self.assertTrue(sampled["do_sample"])
        self.assertEqual(sampled["top_p"], 0.9)
        self.assertEqual(sampled["top_k"], 40)

    def test_cuda_device_map_is_gpu_only_not_auto_offload(self) -> None:
        self.assertEqual(_resolve_device_map("auto"), "auto")
        self.assertEqual(_resolve_device_map("cuda"), 0)
        self.assertEqual(_resolve_device_map("cuda:0"), 0)
        cfg = load_config(PROJECT / "config/default.toml")
        self.assertEqual(cfg.llm.device_map, "cuda:0")
        self.assertTrue(cfg.llm.use_4bit)
        self.assertFalse(cfg.llm.perception.use_cache)
        self.assertTrue(cfg.llm.agent.use_cache)



    def test_span_v1_resolves_only_numbered_source_spans(self) -> None:
        parser = LLMPerceptionService(
            CaptureBackend(),
            LLMPerceptionSettings(protocol="span_v1", ground_actants=True),
        )
        source = "Яблоки бывают зелёные или красные"
        result = parser.parse_response(
            source,
            "A|A1|2|бывать|0|SUBJECT=1|STATE=3-5",
        )
        self.assertEqual(len(result.assertions), 1)
        assertion = result.assertions[0]
        self.assertEqual(assertion.predicate.surface, "бывают")
        self.assertEqual(assertion.predicate.lookup_form, "бывать")
        self.assertEqual(assertion.actants[0].mention, "Яблоки")
        self.assertEqual(assertion.actants[1].mention, "зелёные или красные")
        self.assertEqual(assertion.actants[1].evidence.text, "зелёные или красные")

    def test_span_v1_repair_prompt_repeats_numbered_tokens(self) -> None:
        parser = LLMPerceptionService(
            CaptureBackend(),
            LLMPerceptionSettings(protocol="span_v1"),
        )
        prompt = parser._repair_prompt(
            "Яблоки бывают зелёные",
            "S|EXISTS|surface|lemma|ROLE|NONE",
        )
        self.assertIn("TOKENS:\n1=Яблоки\n2=бывают\n3=зелёные", prompt)
        self.assertIn("BAD OUTPUT:", prompt)

    def test_span_v1_rejects_schema_echo_instead_of_storing_it(self) -> None:
        parser = LLMPerceptionService(
            CaptureBackend(),
            LLMPerceptionSettings(protocol="span_v1", ground_actants=True),
        )
        with self.assertRaises(ValueError):
            parser.parse_response(
                "Яблоки бывают зелёные или красные",
                "S|EXISTS|surface|lemma|ROLE|NONE\nQ|EXISTS|surface|lemma|ROLE_OR_-|NONE",
            )

    def test_span_v1_prompt_contains_only_current_text_not_workspace(self) -> None:
        parser = LLMPerceptionService(
            CaptureBackend(),
            LLMPerceptionSettings(protocol="span_v1"),
        )
        prompt = parser._user_prompt("Яблоки бывают зелёные", InteractionContext())
        self.assertIn("TEXT:\nЯблоки бывают зелёные", prompt)
        self.assertIn("1=Яблоки", prompt)
        self.assertNotIn("ACTIVE MEMORY", prompt)
        self.assertNotIn("CURRENT INPUT", prompt)

    def test_agent_context_echo_without_colons_is_removed(self) -> None:
        class EchoBackend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse(
                    "Привет.\n\nCURRENT INPUT\nПривет\n\nACTIVE MEMORY\ninternal",
                    {},
                )

        agent = LLMAgent(EchoBackend(), LLMAgentSettings())
        answer = agent.respond(AgentContext("Привет", (), (), "# CURRENT INPUT\nПривет"))
        self.assertEqual(answer, "Привет.")

    def test_line_v1_parser_handles_multiple_acts_without_json(self) -> None:
        parser = LLMPerceptionService(
            CaptureBackend(),
            LLMPerceptionSettings(protocol="line_v1", ground_actants=True),
        )
        result = parser.parse_response(
            "Иван сказал, что Мария спит",
            "A|A1|спит|спать|0|SUBJECT=Мария\n"
            "A|A2|сказал|сказать|0|SUBJECT=Иван|OBJECT=@A1",
        )
        self.assertEqual(len(result.assertions), 2)
        self.assertEqual(result.assertions[0].predicate.lookup_form, "спать")
        self.assertEqual(result.assertions[1].actants[1].candidate_ref, "A1")

    def test_line_v1_rejects_ungrounded_prompt_echo_actants(self) -> None:
        parser = LLMPerceptionService(
            CaptureBackend(),
            LLMPerceptionSettings(protocol="line_v1", ground_actants=True),
        )
        with self.assertRaises(ValueError):
            parser.parse_response(
                "Сейчас я напишу полную хуйню",
                "A|A1|напишу|писать|0|SUBJECT=текст|OBJECT=текст",
            )

    def test_parser_failure_is_explicit_and_never_becomes_empty_success(self) -> None:
        class BrokenBackend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse("{ definitely truncated", {})

        parser = LLMPerceptionService(
            BrokenBackend(),
            LLMPerceptionSettings(
                protocol="line_v1",
                repair_attempts=1,
            ),
        )
        with self.assertRaises(PerceptionParseError):
            parser.parse("привет", InteractionContext())
        diag = parser.diagnostics()[-1]
        self.assertIsNone(diag.decoded)
        self.assertIsNotNone(diag.final_error)

    def test_agent_context_echo_is_removed_before_h_boundary(self) -> None:
        class EchoBackend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse(
                    "Привет.\n\nCURRENT INPUT:\nПривет\n\nACTIVE MEMORY:\ninternal",
                    {},
                )

        agent = LLMAgent(EchoBackend(), LLMAgentSettings())
        answer = agent.respond(AgentContext("Привет", (), (), "CURRENT INPUT:\nПривет"))
        self.assertEqual(answer, "Привет.")

    def test_runtime_services_share_one_backend_between_both_roles(self) -> None:
        cfg = load_config(PROJECT / "config/default.toml")
        services = RuntimeServices.build(cfg)
        self.assertIsNotNone(services.llm)
        self.assertIs(services.perception.backend, services.llm)
        self.assertIs(services.agent.backend, services.llm)
        self.assertEqual(cfg.llm.history_messages, 0)



class AdaptiveConditionalRegressionTests(unittest.TestCase):
    class ConditionalMorphology:
        name = "fake_conditional_ru"
        DATA = {
            "если": ("если", "CONJ", None, None, None),
            "лиза": ("лиза", "NOUN", "nomn", "sing", "femn"),
            "получит": ("получить", "VERB", None, "sing", None),
            "получила": ("получить", "VERB", None, "sing", "femn"),
            "советы": ("совет", "NOUN", "accs", "plur", None),
            "она": ("она", "NPRO", "nomn", "sing", "femn"),
            "напишет": ("написать", "VERB", None, "sing", None),
            "текст": ("текст", "NOUN", "accs", "sing", "masc"),
            "прочитает": ("прочитать", "VERB", None, "sing", None),
            "документ": ("документ", "NOUN", "accs", "sing", "masc"),
            "и": ("и", "CONJ", None, None, None),
        }

        def analyze(self, word):
            from ah.perception.morphology import MorphInfo
            item = self.DATA.get(word.casefold())
            if item is None:
                return None
            lemma, pos, case, number, gender = item
            return MorphInfo(lemma, pos, case=case, number=number, gender=gender, score=1.0)

        def analyze_all(self, word):
            item = self.analyze(word)
            return () if item is None else (item,)

    class Backend:
        def __init__(self):
            self.roles = []

        def generate(self, prompt, *, system="", override=None, role="generic"):
            self.roles.append(role)
            if role == "perception_act_type":
                return LLMResponse("1", {})
            fallback = legacy_semantic_answer(role, prompt)
            if fallback is not None:
                return LLMResponse(str(fallback), {})
            raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")

    def _parse(self, text):
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        backend = self.Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.ConditionalMorphology(),
        )
        return parser.parse(text), backend

    def test_fronted_if_clause_is_conditional_not_two_asserted_facts_and_pronoun_corefers(self) -> None:
        from ah.perception import AssertionStatus

        result, backend = self._parse("Если Лиза получит советы, она напишет текст.")
        perception = result.perception
        self.assertEqual(len(perception.assertions), 2)
        receive, write = perception.assertions
        self.assertEqual(receive.predicate.lookup_form, "получить")
        self.assertEqual(write.predicate.lookup_form, "написать")
        self.assertEqual(receive.status, AssertionStatus.CONDITIONAL)
        self.assertEqual(write.status, AssertionStatus.CONDITIONAL)
        self.assertEqual(len(perception.conditionals), 1)
        conditional = perception.conditionals[0]
        self.assertEqual(conditional.antecedent_refs, (receive.local_id,))
        self.assertEqual(conditional.consequent_refs, (write.local_id,))
        self.assertEqual(conditional.evidence.text, "Если")

        lisa = next(a for a in receive.actants if a.role == ActantRole.SUBJECT)
        pronoun = next(a for a in write.actants if a.role == ActantRole.SUBJECT)
        self.assertIsNotNone(lisa.entity_ref)
        self.assertEqual(lisa.entity_ref, pronoun.entity_ref)

    def test_postposed_if_clause_uses_same_conditional_compiler_and_inherits_subject(self) -> None:
        from ah.perception import AssertionStatus

        result, backend = self._parse("Лиза напишет текст, если получит советы.")
        perception = result.perception
        self.assertEqual(len(perception.assertions), 2)
        write, receive = perception.assertions
        self.assertTrue(all(a.status == AssertionStatus.CONDITIONAL for a in perception.assertions))
        conditional = perception.conditionals[0]
        self.assertEqual(conditional.antecedent_refs, (receive.local_id,))
        self.assertEqual(conditional.consequent_refs, (write.local_id,))
        write_subject = next(a for a in write.actants if a.role == ActantRole.SUBJECT)
        receive_subject = next(a for a in receive.actants if a.role == ActantRole.SUBJECT)
        self.assertIsNotNone(write_subject.entity_ref)
        self.assertEqual(write_subject.entity_ref, receive_subject.entity_ref)

    def test_compound_consequent_uses_predicate_local_arguments_and_shared_subject_identity(self) -> None:
        from ah.integration.candidate_validator import CandidateValidator

        result, backend = self._parse(
            "Если Лиза получит советы, она прочитает документ и напишет текст."
        )
        perception = result.perception
        self.assertEqual(len(perception.assertions), 3)
        receive, read, write = perception.assertions
        conditional = perception.conditionals[0]
        self.assertEqual(conditional.antecedent_refs, (receive.local_id,))
        self.assertEqual(conditional.consequent_refs, (read.local_id, write.local_id))

        read_roles = {a.role: a for a in read.actants}
        write_roles = {a.role: a for a in write.actants}
        receive_subject = next(a for a in receive.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(read_roles[ActantRole.OBJECT].mention, "документ")
        self.assertEqual(write_roles[ActantRole.OBJECT].mention, "текст")
        self.assertEqual(read_roles[ActantRole.SUBJECT].mention, "она")
        self.assertEqual(write_roles[ActantRole.SUBJECT].mention, "она")
        self.assertIsNotNone(receive_subject.entity_ref)
        self.assertEqual(read_roles[ActantRole.SUBJECT].entity_ref, receive_subject.entity_ref)
        self.assertEqual(write_roles[ActantRole.SUBJECT].entity_ref, receive_subject.entity_ref)
        self.assertEqual(read.evidence.text, "она прочитает документ")
        self.assertEqual(write.evidence.text, "напишет текст")
        self.assertIsNone(write.predicate.template_candidate)
        CandidateValidator().validate(perception)

    def test_coordinated_subject_inheritance_survives_intermediate_case_ambiguity(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception.morphology import MorphInfo

        class AmbiguousMorphology(self.ConditionalMorphology):
            def analyze_all(self, word):
                if word.casefold() == "документ":
                    return (
                        MorphInfo("документ", "NOUN", case="accs", number="sing", gender="masc", score=0.6),
                        MorphInfo("документ", "NOUN", case="nomn", number="sing", gender="masc", score=0.4),
                    )
                return super().analyze_all(word)

        backend = self.Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=AmbiguousMorphology(),
        )
        perception = parser.parse(
            "Если Лиза получит советы, она прочитает документ и напишет текст."
        ).perception
        receive, read, write = perception.assertions
        receive_subject = next(a for a in receive.actants if a.role == ActantRole.SUBJECT)
        read_subject = next(a for a in read.actants if a.role == ActantRole.SUBJECT)
        write_subject = next(a for a in write.actants if a.role == ActantRole.SUBJECT)

        self.assertEqual(write_subject.mention, "она")
        self.assertEqual(write_subject.evidence, read_subject.evidence)
        self.assertEqual(write_subject.entity_ref, read_subject.entity_ref)
        self.assertEqual(write_subject.entity_ref, receive_subject.entity_ref)

    def test_compound_antecedent_is_one_and_group_not_two_independent_conditions(self) -> None:
        from ah.integration.candidate_validator import CandidateValidator

        result, backend = self._parse(
            "Если Лиза получит советы и прочитает документ, она напишет текст."
        )
        perception = result.perception
        self.assertEqual(len(perception.assertions), 3)
        receive, read, write = perception.assertions
        conditional = perception.conditionals[0]
        self.assertEqual(conditional.antecedent_refs, (receive.local_id, read.local_id))
        self.assertEqual(conditional.consequent_refs, (write.local_id,))

        receive_subject = next(a for a in receive.actants if a.role == ActantRole.SUBJECT)
        read_subject = next(a for a in read.actants if a.role == ActantRole.SUBJECT)
        write_subject = next(a for a in write.actants if a.role == ActantRole.SUBJECT)
        self.assertIsNotNone(receive_subject.entity_ref)
        self.assertEqual(read_subject.entity_ref, receive_subject.entity_ref)
        self.assertEqual(write_subject.entity_ref, receive_subject.entity_ref)
        self.assertEqual(next(a for a in receive.actants if a.role == ActantRole.OBJECT).mention, "советы")
        self.assertEqual(next(a for a in read.actants if a.role == ActantRole.OBJECT).mention, "документ")
        self.assertEqual(next(a for a in write.actants if a.role == ActantRole.OBJECT).mention, "текст")
        CandidateValidator().validate(perception)

if __name__ == "__main__":
    unittest.main()

class MorphologyAssistedAdaptiveParserTests(unittest.TestCase):
    class FakeMorphology:
        name = "fake_ru"
        DATA = {
            "яблоки": ("яблоко", "NOUN", "nomn", "plur"),
            "яблоко": ("яблоко", "NOUN", "nomn", "sing"),
            "бывают": ("бывать", "VERB", None, "plur"),
            "бывает": ("бывать", "VERB", None, "sing"),
            "красные": ("красный", "ADJF", "nomn", "plur"),
            "зелёные": ("зелёный", "ADJF", "nomn", "plur"),
            "красное": ("красный", "ADJF", "nomn", "sing"),
            "зелёное": ("зелёный", "ADJF", "nomn", "sing"),
            "и": ("и", "CONJ", None, None),
            "или": ("или", "CONJ", None, None),
            "иван": ("иван", "NOUN", "nomn", "sing"),
            "мария": ("мария", "NOUN", "nomn", "sing"),
            "сказал": ("сказать", "VERB", None, "sing"),
            "спит": ("спать", "VERB", None, "sing"),
            "что": ("что", "CONJ", None, None),
            "пётр": ("пётр", "NOUN", "nomn", "sing"),
            "пришёл": ("прийти", "VERB", None, "sing"),
            "пришли": ("прийти", "VERB", None, "plur"),
            "ушёл": ("уйти", "VERB", None, "sing"),
            "ушла": ("уйти", "VERB", None, "sing"),
            "ушли": ("уйти", "VERB", None, "plur"),
            "хочет": ("хотеть", "VERB", None, "sing"),
            "работать": ("работать", "INFN", None, None),
        }

        def analyze(self, word):
            from ah.perception.morphology import MorphInfo
            item = self.DATA.get(word.casefold())
            if item is None:
                return None
            lemma, pos, case, number = item
            return MorphInfo(lemma, pos, case=case, number=number, score=1.0)

    def test_morphology_makes_simple_russian_copular_assertion_almost_fully_deterministic(self) -> None:
        from ah.perception.adaptive_parser import AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception.morphology import NullMorphology

        class Backend:
            def __init__(self):
                self.roles = []
                self.answers = ["1"]
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role != "perception_act_type":
                    fallback = legacy_semantic_answer(role, prompt)
                    if fallback is not None:
                        return LLMResponse(str(fallback), {})
                    raise AssertionError(f"unexpected LLM probe: {role}")
                return LLMResponse(self.answers.pop(0), {})

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Яблоки бывают зелёные и красные")
        self.assertEqual(len(result.perception.assertions), 1)
        assertion = result.perception.assertions[0]
        self.assertEqual(assertion.predicate.surface, "бывают")
        self.assertIn(assertion.predicate.lookup_form, {"быть", "бывать"})
        self.assertEqual(
            {a.role: a.mention for a in assertion.actants},
            {ActantRole.SUBJECT: "Яблоки", ActantRole.STATE: "зелёные и красные"},
        )
        deterministic = [t for t in result.traces if t.raw_text.startswith("<deterministic")]
        self.assertTrue(any(t.stage == "predicate_start" and t.normalized_answer == "2" for t in deterministic))
        self.assertTrue(any(t.stage == "predicate_end" and t.normalized_answer == "2" for t in deterministic))
        self.assertTrue(any(t.stage == "predicate_symbol" and t.normalized_answer == "бывать" for t in deterministic))
        self.assertTrue(any(t.stage == "actant_deterministic" and "STATE" in (t.normalized_answer or "") for t in deterministic))


    def test_coordination_is_exposed_as_structured_or_candidate(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception import CompositionOperator

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}")

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Яблоки бывают зелёные или красные")
        state = next(a for a in result.perception.assertions[0].actants if a.role == ActantRole.STATE)
        self.assertIsNotNone(state.composition)
        self.assertEqual(state.composition.operator, CompositionOperator.OR)
        self.assertEqual([m.mention for m in state.composition.members], ["зелёные", "красные"])

    def test_subordinate_clause_becomes_nested_candidate_ref(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["1"],
                    "perception_predicate_start": ["2"],
                    "perception_predicate_symbol": ["sleep"],
                    "perception_frame_relation": ["CONTENT_LINK"],
                }
            def generate(self, prompt, *, system="", override=None, role="generic"):
                values = self.answers.get(role)
                if not values:
                    fallback = legacy_semantic_answer(role, prompt)
                    if fallback is not None:
                        return LLMResponse(str(fallback), {})
                    raise AssertionError(f"unexpected LLM probe: {role}")
                return LLMResponse(values.pop(0), {})

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван сказал, что Мария спит")
        self.assertEqual(len(result.perception.assertions), 2)
        parent, child = result.perception.assertions
        nested = next(a for a in parent.actants if a.candidate_ref is not None)
        self.assertEqual(nested.role, ActantRole.OBJECT)
        self.assertEqual(nested.candidate_ref, child.local_id)
        self.assertEqual([(a.role, a.mention) for a in child.actants if a.mention], [(ActantRole.SUBJECT, "Мария")])


    def test_active_probe_requests_never_contain_demonstration_anchors(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.prompts = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.prompts.append((prompt, system))
                return LLMResponse("1", {})

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
        )
        try:
            parser.parse("тест")
        except Exception:
            pass
        joined = "\n".join(prompt + "\n" + system for prompt, system in backend.prompts).casefold()
        for anchor in ("for example", "e.g.", "example output", "например"):
            self.assertNotIn(anchor, joined)

    def test_alternative_morphology_parse_can_supply_nominative_subject(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception.morphology import MorphInfo

        class AmbiguousMorphology(self.FakeMorphology):
            def analyze_all(self, word):
                if word.casefold() == "яблоки":
                    return (
                        MorphInfo("яблоко", "NOUN", case="gent", number="sing", score=0.6),
                        MorphInfo("яблоко", "NOUN", case="nomn", number="plur", score=0.4),
                    )
                one = self.analyze(word)
                return () if one is None else (one,)

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=AmbiguousMorphology(),
        )
        result = parser.parse("Яблоки бывают зелёные и красные")
        subject = next(a for a in result.perception.assertions[0].actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(subject.mention, "Яблоки")


    def test_coordinated_independent_clauses_stay_independent_frames(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван пришёл и Пётр ушёл")
        self.assertEqual(len(result.perception.assertions), 2)
        first, second = result.perception.assertions
        self.assertEqual(first.predicate.lookup_form, "прийти")
        self.assertEqual(second.predicate.lookup_form, "уйти")
        self.assertFalse(any(a.candidate_ref for a in first.actants))
        self.assertFalse(any(a.candidate_ref for a in second.actants))

    def test_same_clause_predicate_frames_can_nest_via_discrete_relation_probe(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                if role == "perception_frame_relation":
                    return LLMResponse("CONTENT_LINK", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван хочет работать")
        self.assertEqual(len(result.perception.assertions), 2)
        parent, child = result.perception.assertions
        self.assertEqual(parent.predicate.lookup_form, "хотеть")
        self.assertEqual(child.predicate.lookup_form, "работать")
        ref = next(a for a in parent.actants if a.candidate_ref is not None)
        self.assertEqual(ref.candidate_ref, child.local_id)
        self.assertEqual(ref.role, ActantRole.OBJECT)
        self.assertIn("perception_frame_relation", backend.roles)

    def test_morphology_can_represent_zero_copula_as_implicit_be(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}")

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Яблоко красное")
        assertion = result.perception.assertions[0]
        self.assertIn(assertion.predicate.lookup_form, {"быть", "бывать"})
        self.assertEqual({a.role: a.mention for a in assertion.actants}, {
            ActantRole.SUBJECT: "Яблоко",
            ActantRole.STATE: "красное",
        })


    def test_subject_coordination_becomes_structured_and_without_llm_role_guess(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception import CompositionOperator

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван и Пётр пришли")
        assertion = result.perception.assertions[0]
        subject = next(a for a in assertion.actants if a.role == ActantRole.SUBJECT)
        self.assertIsNotNone(subject.composition)
        self.assertEqual(subject.composition.operator, CompositionOperator.AND)
        self.assertEqual([m.mention for m in subject.composition.members], ["Иван", "Пётр"])

    def test_ambiguous_subordinate_relation_can_abstain_without_inventing_candidate_ref(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                if role == "perception_frame_relation":
                    if "SEPARATE" in prompt:
                        return LLMResponse("SEPARATE", {})
                    raise AssertionError(f"unexpected frame-relation protocol\n{prompt}")
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван сказал, что Мария спит")
        self.assertEqual(len(result.perception.assertions), 2)
        self.assertFalse(any(a.candidate_ref for item in result.perception.assertions for a in item.actants))

    def test_predicate_boundary_probe_has_explicit_abstention_and_never_forces_span(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings, AdaptiveParseError
        from ah.perception.morphology import NullMorphology

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                if role == "perception_predicate_start":
                    return LLMResponse("1", {})
                if role == "perception_predicate_end":
                    self.last_prompt = prompt
                    return LLMResponse("0", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=NullMorphology(),
        )
        with self.assertRaises(AdaptiveParseError):
            parser.parse("alpha beta")
        self.assertIn("[0] cannot determine the predicate boundary reliably", backend.last_prompt)

    def test_active_probe_files_contain_no_demonstration_examples(self) -> None:
        joined = "\n".join(
            path.read_text(encoding="utf-8")
            for path in (PROJECT / "prompts/perception").glob("*.txt")
        )
        lowered = joined.casefold()
        for anchor in ("for example", "e.g.", "example", "sample output", "например"):
            self.assertNotIn(anchor, lowered)

    def test_missing_probe_instruction_fails_instead_of_substituting_hidden_prompt(self) -> None:
        from tempfile import TemporaryDirectory
        from ah.perception.adaptive_parser import AdaptiveParseError, AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception.morphology import NullMorphology

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                raise AssertionError("backend must not be called without an explicit prompt")

        with TemporaryDirectory() as tmp:
            prompt_dir = Path(tmp)
            (prompt_dir / "probe_system.txt").write_text("Return only the requested value.", encoding="utf-8")
            parser = AdaptivePerceptionParser(
                Backend(),
                AdaptiveSettings(
                    prompt_dir=prompt_dir,
                    generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                    retry_attempts=0,
                    morphology_backend="none",
                ),
                morphology=NullMorphology(),
            )
            with self.assertRaisesRegex(AdaptiveParseError, "required adaptive prompt is missing"):
                parser.parse("alpha")


    def test_coordinated_predicates_share_subject_without_forced_nesting(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван пришёл и ушёл")
        self.assertEqual(len(result.perception.assertions), 2)
        first, second = result.perception.assertions
        self.assertEqual(first.predicate.lookup_form, "прийти")
        self.assertEqual(second.predicate.lookup_form, "уйти")
        for item in (first, second):
            subject = next(a for a in item.actants if a.role == ActantRole.SUBJECT)
            self.assertEqual(subject.mention, "Иван")
            self.assertFalse(any(a.candidate_ref for a in item.actants))

    def test_coordinated_predicates_reuse_structured_group_subject(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван и Мария пришли и ушли")
        self.assertEqual(len(result.perception.assertions), 2)
        subjects = [
            next(a for a in item.actants if a.role == ActantRole.SUBJECT)
            for item in result.perception.assertions
        ]
        self.assertTrue(all(subject.composition is not None for subject in subjects))
        self.assertEqual(subjects[0].composition, subjects[1].composition)

    def test_explicit_subject_after_coordinator_is_not_inherited(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(role)

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.FakeMorphology(),
        )
        result = parser.parse("Иван пришёл и Мария ушла")
        self.assertEqual(len(result.perception.assertions), 2)
        first, second = result.perception.assertions
        self.assertEqual(next(a for a in first.actants if a.role == ActantRole.SUBJECT).mention, "Иван")
        self.assertEqual(next(a for a in second.actants if a.role == ActantRole.SUBJECT).mention, "Мария")



class StructuralMorphologyConfidenceTests(unittest.TestCase):
    def test_rare_verb_reading_does_not_create_predicate_head(self) -> None:
        from ah.perception.linguistic_candidates import LinguisticCandidateBuilder
        from ah.perception.morphology import MorphInfo

        class Morphology:
            name = "test"
            def analyze_all(self, word):
                mapping = {
                    "иван": (MorphInfo("иван", "NOUN", case="nomn", score=1.0),),
                    "любит": (MorphInfo("любить", "VERB", mood="indc", score=1.0),),
                    "чай": (
                        MorphInfo("чай", "NOUN", case="nomn", score=0.571428),
                        MorphInfo("чай", "NOUN", case="accs", score=0.285714),
                        MorphInfo("чаять", "VERB", mood="impr", score=0.142857),
                    ),
                }
                return mapping.get(word.casefold(), ())
            def analyze(self, word):
                values = self.analyze_all(word)
                return values[0] if values else None

        graph = LinguisticCandidateBuilder(Morphology()).build("Иван любит чай.")
        self.assertEqual(
            [(item.token_index, item.lemma_candidates) for item in graph.predicates],
            [(2, ("любить",))],
        )

    def test_tiny_noun_reading_of_conjunction_cannot_become_subject(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception.morphology import MorphInfo

        class Morphology:
            name = "test"
            def analyze_all(self, word):
                mapping = {
                    "лиза": (MorphInfo("лиза", "NOUN", case="nomn", score=1.0),),
                    "взяла": (MorphInfo("взять", "VERB", mood="indc", score=1.0),),
                    "книгу": (MorphInfo("книга", "NOUN", case="accs", score=1.0),),
                    "открыла": (MorphInfo("открыть", "VERB", mood="indc", score=1.0),),
                    "её": (
                        MorphInfo("её", "ADJF", case="gent", score=0.074),
                        MorphInfo("она", "NPRO", case="accs", score=0.037),
                    ),
                    "и": (
                        MorphInfo("и", "CONJ", score=0.998),
                        MorphInfo("и", "NOUN", case="nomn", score=0.0001),
                    ),
                    "прочитала": (MorphInfo("прочитать", "VERB", mood="indc", score=1.0),),
                }
                return mapping.get(word.casefold(), ())
            def analyze(self, word):
                values = self.analyze_all(word)
                return values[0] if values else None

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_role_participant":
                    return LLMResponse("OBJECT", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}")

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                verify_predicate_symbol=True,
            ),
            morphology=Morphology(),
        )
        result = parser.parse("Лиза взяла книгу, открыла её и прочитала.")
        self.assertEqual(len(result.perception.assertions), 3)
        third = result.perception.assertions[2]
        subject = next(a for a in third.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(subject.mention, "Лиза")
        self.assertNotEqual(subject.mention, "её и")
        self.assertIsNone(third.predicate.template_candidate)


class AdaptivePredicateSymbolRegressionTests(unittest.TestCase):
    def test_common_give_symbol_has_deterministic_fast_path(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser
        self.assertEqual(AdaptivePerceptionParser._deterministic_predicate_symbol("давать"), "давать")
        self.assertEqual(AdaptivePerceptionParser._deterministic_predicate_symbol("дать"), "дать")

    def test_adaptive_v3_unknown_symbol_uses_source_lexical_form_without_llm_naming(self) -> None:
        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["1", "0"],
                    "perception_predicate_start": ["2"],
                    "perception_predicate_end": ["2"],
                    "perception_actant_start": ["1"],
                    "perception_role_cue": ["ACTOR_OR_EXPERIENCER"],
                }
                self.calls = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.calls.append((role, prompt))
                return LLMResponse(self.answers[role].pop(0), {})

        backend = Backend()
        parser = LLMPerceptionService(
            backend,
            LLMPerceptionSettings(
                protocol="adaptive_v3",
                morphology_backend="none",
                probe_prompt_dir=PROJECT / "prompts/perception",
                probe_retry_attempts=0,
            ),
        )
        result = parser.parse("Иван кувыркался", InteractionContext())
        self.assertEqual(len(result.assertions), 1)
        self.assertEqual(result.assertions[0].predicate.lookup_form, "кувыркался")
        self.assertFalse(any(role == "perception_predicate_symbol" for role, _ in backend.calls))
        self.assertFalse(any(role == "perception_predicate_symbol_verify" for role, _ in backend.calls))

    def test_adaptive_v3_unknown_later_symbol_does_not_require_open_text_generation(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings
        from ah.perception.morphology import MorphInfo

        class Morphology:
            name = "test"
            def analyze_all(self, word):
                mapping = {
                    "писал": (MorphInfo("писать", "VERB", mood="indc", score=1.0),),
                    "кувыркался": (MorphInfo("кувыркаться", "VERB", mood="indc", score=1.0),),
                    "и": (MorphInfo("и", "CONJ", score=1.0),),
                }
                return mapping.get(word.casefold(), ())
            def analyze(self, word):
                values = self.analyze_all(word)
                return values[0] if values else None

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}")

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
                verify_predicate_symbol=True,
            ),
            morphology=Morphology(),
        )
        result = parser.parse("писал и кувыркался")
        self.assertEqual(len(result.perception.assertions), 2)
        self.assertEqual(result.perception.assertions[1].predicate.lookup_form, "кувыркаться")



class AdaptiveFunctionWordRegressionTests(unittest.TestCase):
    class NegationMorphology:
        name = "fake_negation_ru"
        DATA = {
            "я": ("я", "NPRO", "nomn"),
            "лиза": ("лиза", "NOUN", "nomn"),
            "не": ("не", "PRCL", None),
            "знаю": ("знать", "VERB", None),
            "что": ("что", "CONJ", None),
            "писала": ("писать", "VERB", None),
            "текст": ("текст", "NOUN", "accs"),
            "давала": ("давать", "VERB", None),
            "мне": ("я", "NPRO", "datv"),
            "советы": ("совет", "NOUN", "accs"),
            "никто": ("никто", "NPRO", "nomn"),
            "пришёл": ("прийти", "VERB", None),
        }

        def analyze(self, word):
            from ah.perception.morphology import MorphInfo
            item = self.DATA.get(word.casefold())
            if item is None:
                return None
            lemma, pos, case = item
            return MorphInfo(lemma, pos, case=case, score=1.0)

        def analyze_all(self, word):
            item = self.analyze(word)
            return () if item is None else (item,)

    def test_negation_particle_is_not_reused_as_actant(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}")

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.NegationMorphology(),
        )
        result = parser.parse("Лиза не давала мне советы")
        assertion = result.perception.assertions[0]
        self.assertTrue(assertion.negated)
        self.assertEqual(
            [(a.role, a.mention) for a in assertion.actants],
            [
                (ActantRole.SUBJECT, "Лиза"),
                (ActantRole.RECIPIENT, "мне"),
                (ActantRole.OBJECT, "советы"),
            ],
        )
        self.assertNotIn("не", [a.mention for a in assertion.actants])


    def test_matrix_negation_does_not_leak_into_embedded_clause(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                if role == "perception_frame_relation":
                    return LLMResponse("CONTENT_LINK", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.NegationMorphology(),
        )
        result = parser.parse("Я не знаю, что Лиза писала текст.")
        self.assertEqual(len(result.perception.assertions), 2)
        parent, child = result.perception.assertions
        self.assertEqual(parent.predicate.lookup_form, "знать")
        self.assertTrue(parent.negated)
        self.assertEqual(child.predicate.lookup_form, "писать")
        self.assertFalse(child.negated)
        self.assertTrue(any(a.candidate_ref == child.local_id for a in parent.actants))
        self.assertNotIn("perception_negation", backend.roles)

    def test_embedded_negation_does_not_leak_into_matrix_clause(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []
            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                if role == "perception_frame_relation":
                    return LLMResponse("CONTENT_LINK", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.NegationMorphology(),
        )
        result = parser.parse("Я знаю, что Лиза не писала текст.")
        self.assertEqual(len(result.perception.assertions), 2)
        parent, child = result.perception.assertions
        self.assertEqual(parent.predicate.lookup_form, "знать")
        self.assertFalse(parent.negated)
        self.assertEqual(child.predicate.lookup_form, "писать")
        self.assertTrue(child.negated)
        self.assertTrue(any(a.candidate_ref == child.local_id for a in parent.actants))
        self.assertNotIn("perception_negation", backend.roles)

    def test_negative_pronoun_remains_content_bearing_subject(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                if role == "perception_act_type":
                    return LLMResponse("1", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}")

        parser = AdaptivePerceptionParser(
            Backend(),
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.NegationMorphology(),
        )
        result = parser.parse("Никто не пришёл")
        assertion = result.perception.assertions[0]
        subject = next(a for a in assertion.actants if a.role == ActantRole.SUBJECT)
        self.assertEqual(subject.mention, "Никто")
        self.assertTrue(assertion.negated)
        self.assertNotIn("не", [a.mention for a in assertion.actants])


class AdaptiveComplexClauseRegressionTests(unittest.TestCase):
    class ComplexMorphology:
        name = "fake_complex_ru"
        DATA = {
            "я": ("я", "NPRO", "nomn"),
            "прочитал": ("прочитать", "VERB", None),
            "текст": ("текст", "NOUN", "accs"),
            "который": ("который", "ADJF", "accs"),
            "лиза": ("лиза", "NOUN", "nomn"),
            "написала": ("написать", "VERB", None),
            "после": ("после", "PREP", None),
            "до": ("до", "PREP", None),
            "того": ("тот", "NPRO", "gent"),
            "как": ("как", "CONJ", None),
            "когда": ("когда", "CONJ", None),
            "получила": ("получить", "VERB", None),
            "советы": ("совет", "NOUN", "accs"),
            "от": ("от", "PREP", None),
            "ивана": ("иван", "NOUN", "gent"),
        }

        def analyze(self, word):
            from ah.perception.morphology import MorphInfo
            item = self.DATA.get(word.casefold())
            if item is None:
                return None
            lemma, pos, case = item
            return MorphInfo(lemma, pos, case=case, score=1.0)

        def analyze_all(self, word):
            item = self.analyze(word)
            return () if item is None else (item,)

    def test_relative_clause_and_compound_temporal_connector_compose_without_fake_actants(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("PARENT_ARGUMENT", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.ComplexMorphology(),
        )
        result = parser.parse(
            "Я прочитал текст, который Лиза написала после того, как получила советы от Ивана.",
            structural_resolution="PREDICATE_ATTACHMENT",
        )
        self.assertEqual(len(result.perception.assertions), 3)
        read, write, receive = result.perception.assertions

        self.assertEqual(read.predicate.lookup_form, "прочитать")
        self.assertEqual(
            [(a.role, a.mention, a.candidate_ref) for a in read.actants],
            [
                (ActantRole.SUBJECT, "Я", None),
                (ActantRole.OBJECT, "текст", None),
            ],
        )

        self.assertEqual(write.predicate.lookup_form, "написать")
        self.assertEqual(
            [(a.role, a.mention, a.candidate_ref) for a in write.actants],
            [
                (ActantRole.SUBJECT, "Лиза", None),
                (ActantRole.OBJECT, "текст", None),
            ],
        )

        self.assertEqual(receive.predicate.lookup_form, "получить")
        self.assertEqual(
            [(a.role, a.mention, a.candidate_ref) for a in receive.actants],
            [
                (ActantRole.OBJECT, "советы", None),
                (ActantRole.SOURCE, "Ивана", None),
                (ActantRole.SUBJECT, "Лиза", None),
            ],
        )
        flattened_mentions = [a.mention for assertion in result.perception.assertions for a in assertion.actants]
        self.assertNotIn("который Лиза", flattened_mentions)
        self.assertNotIn("после того", flattened_mentions)
        self.assertNotIn("как", flattened_mentions)

        read_object = next(a for a in read.actants if a.role == ActantRole.OBJECT)
        write_object = next(a for a in write.actants if a.role == ActantRole.OBJECT)
        self.assertIsNotNone(read_object.entity_ref)
        self.assertEqual(read_object.entity_ref, write_object.entity_ref)

        write_subject = next(a for a in write.actants if a.role == ActantRole.SUBJECT)
        receive_subject = next(a for a in receive.actants if a.role == ActantRole.SUBJECT)
        self.assertIsNotNone(write_subject.entity_ref)
        self.assertEqual(write_subject.entity_ref, receive_subject.entity_ref)

        source = next(a for a in receive.actants if a.role == ActantRole.SOURCE)
        self.assertEqual(source.normalized_hint, "Иван")
        self.assertEqual(source.evidence.text, "от Ивана")

        self.assertEqual(read.evidence.text, "Я прочитал текст")
        self.assertEqual(write.evidence.text, "который Лиза написала")
        self.assertEqual(receive.evidence.text, "после того, как получила советы от Ивана")

        self.assertEqual(len(result.perception.relations), 1)
        temporal = result.perception.relations[0]
        self.assertEqual(temporal.relation_id, "FOLLOW")
        self.assertEqual(temporal.source_ref, receive.local_id)
        self.assertEqual(temporal.target_ref, write.local_id)
        self.assertEqual(temporal.evidence.text, "после того, как")
        self.assertIn("perception_role_cue", backend.roles)

    def test_before_after_and_when_have_distinct_temporal_semantics(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("PARENT_ARGUMENT", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")

        def parse(text):
            backend = Backend()
            parser = AdaptivePerceptionParser(
                backend,
                AdaptiveSettings(
                    prompt_dir=PROJECT / "prompts/perception",
                    generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                    retry_attempts=0,
                    morphology_backend="none",
                ),
                morphology=self.ComplexMorphology(),
            )
            return parser.parse(text).perception

        after = parse("Лиза написала текст после того, как получила советы.")
        self.assertEqual(len(after.relations), 1)
        self.assertEqual((after.relations[0].source_ref, after.relations[0].target_ref), ("A2", "A1"))

        before = parse("Лиза написала текст до того, как получила советы.")
        self.assertEqual(len(before.relations), 1)
        self.assertEqual((before.relations[0].source_ref, before.relations[0].target_ref), ("A1", "A2"))

        simultaneous = parse("Лиза написала текст, когда получила советы.")
        self.assertEqual(simultaneous.relations, ())
        self.assertTrue(any(a.role == ActantRole.TIME and a.candidate_ref == "A2" for a in simultaneous.assertions[0].actants))

    def test_causal_clause_emits_semantic_cause_relation_from_frame_attachment(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser, AdaptiveSettings

        class Backend:
            def __init__(self):
                self.roles = []

            def generate(self, prompt, *, system="", override=None, role="generic"):
                self.roles.append(role)
                if role == "perception_act_type":
                    return LLMResponse("PARENT_ARGUMENT", {})
                fallback = legacy_semantic_answer(role, prompt)
                if fallback is not None:
                    return LLMResponse(str(fallback), {})
                raise AssertionError(f"unexpected LLM probe: {role}\n{prompt}")

        backend = Backend()
        parser = AdaptivePerceptionParser(
            backend,
            AdaptiveSettings(
                prompt_dir=PROJECT / "prompts/perception",
                generation=LLMRoleSettings(max_new_tokens=24, temperature=0.0),
                retry_attempts=0,
                morphology_backend="none",
            ),
            morphology=self.ComplexMorphology(),
        )
        result = parser.parse(
            "Лиза написала текст потому, что получила советы от Ивана.",
            structural_resolution="PREDICATE_ATTACHMENT",
        ).perception

        self.assertEqual(len(result.assertions), 2)
        write, receive = result.assertions
        self.assertFalse(any(a.role == ActantRole.CAUSE for a in write.actants))
        self.assertEqual(len(result.relations), 1)
        relation = result.relations[0]
        self.assertEqual(relation.relation_id, "CAUSE")
        self.assertEqual((relation.source_ref, relation.target_ref), (receive.local_id, write.local_id))
        self.assertEqual(relation.evidence.text, "потому, что")
        self.assertIn("perception_role_cue", backend.roles)

    def test_repeated_identical_open_symbol_is_format_noise_not_semantic_ambiguity(self) -> None:
        from ah.perception.adaptive_parser import AdaptivePerceptionParser

        self.assertEqual(AdaptivePerceptionParser._english_symbol("read\n\nread\nread\n"), "read")
        with self.assertRaises(Exception):
            AdaptivePerceptionParser._english_symbol("read\nwrite\n")
