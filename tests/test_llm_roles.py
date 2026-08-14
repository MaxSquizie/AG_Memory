from __future__ import annotations

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
from ah.perception import LLMPerceptionService, LLMPerceptionSettings
from ah.model import ActantRole, Domain
from ah.core import AHCore, SequentialUidGenerator
from ah.perception import PredicateCandidate, TextSensoryService
from ah.integration.template_resolver import TemplateResolver
from ah.llm.worker import _resolve_loader_type, _resolve_device_map, _generation_config_values, generate as worker_generate
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
        self.assertEqual(cfg.llm.perception_protocol, "adaptive_v2")
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

    def test_adaptive_parser_uses_explicit_numeric_choices_and_english_predicate_symbol(self) -> None:
        class ScriptedBackend:
            def __init__(self):
                self.calls = []
                self.answers = {
                    "perception_act_type": ["1", "0"],
                    "perception_predicate_start": ["2"],
                    "perception_predicate_end": ["2"],
                    "perception_predicate_symbol": ["be"],
                    "perception_actant_start": ["1", "3"],
                    "perception_actant_end": ["5"],
                    "perception_role_family": ["1", "2"],
                    "perception_role_participant": ["1"],
                    "perception_role_description": ["1"],
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
        result = parser.parse("Яблоки бывают красные или зелёные", InteractionContext())
        self.assertEqual(len(result.assertions), 1)
        assertion = result.assertions[0]
        self.assertEqual(assertion.predicate.surface, "бывают")
        self.assertEqual(assertion.predicate.lookup_form, "be")
        self.assertFalse(assertion.negated)
        self.assertEqual([(a.role, a.mention) for a in assertion.actants], [
            (ActantRole.SUBJECT, "Яблоки"),
            (ActantRole.STATE, "красные или зелёные"),
        ])
        self.assertTrue(all(call[0].startswith("perception_") for call in backend.calls))
        self.assertTrue(all(len(call[2]) < 360 for call in backend.calls))
        self.assertTrue(all(call[3]["max_new_tokens"] <= 10 for call in backend.calls))
        self.assertNotIn("perception_negation", [call[0] for call in backend.calls])
        diag = parser.diagnostics()[-1]
        self.assertTrue(all(a.prompt for a in diag.attempts))
        self.assertEqual(diag.attempts[0].normalized_answer, "ASSERTION")
        self.assertTrue(any(a.raw_text == "<deterministic>" for a in diag.attempts))

    def test_adaptive_query_fill_role_is_built_from_numeric_choices(self) -> None:
        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["2", "0"],
                    "perception_predicate_start": ["2"],
                    "perception_predicate_end": ["2"],
                    "perception_predicate_symbol": ["love"],
                    "perception_query_mode": ["2"],
                    "perception_role_family": ["1", "1"],
                    "perception_role_participant": ["1", "1"],
                    "perception_actant_start": ["3"],
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

    def test_adaptive_command_uses_same_discrete_span_and_role_pipeline(self) -> None:
        class Backend:
            def __init__(self):
                self.answers = {
                    "perception_act_type": ["3", "0"],
                    "perception_predicate_start": ["1"],
                    "perception_predicate_end": ["1"],
                    "perception_predicate_symbol": ["open"],
                    "perception_actant_start": ["2"],
                    "perception_role_family": ["1"],
                    "perception_role_participant": ["2"],
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
                    "perception_actant_start": ["1.", "3."],
                    "perception_actant_end": ["5."],
                    "perception_role_family": ["1.", "2."],
                    "perception_role_participant": ["1."],
                    "perception_role_description": ["1."],
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
        result = parser.parse("Яблоки бывают красные или зелёные", InteractionContext())
        self.assertEqual(len(result.assertions), 1)
        assertion = result.assertions[0]
        self.assertEqual(assertion.predicate.lookup_form, "be")
        self.assertEqual([(a.role, a.mention) for a in assertion.actants], [
            (ActantRole.SUBJECT, "Яблоки"),
            (ActantRole.STATE, "красные или зелёные"),
        ])

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
                failure_policy="empty",
            ),
        )
        result = parser.parse("Яблоки бывают красные", InteractionContext())
        self.assertEqual(result.acts_count, 0)
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
                    return LLMResponse("0", {})
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

    def test_adaptive_v2_prompts_define_choices_and_do_not_require_ah_vocabulary(self) -> None:
        probe_dir = PROJECT / "prompts/perception"
        joined = "\n".join(path.read_text(encoding="utf-8") for path in probe_dir.glob("*.txt"))
        for unexplained in ("N-M", "ActantRole", "UID", "hypernode", "AH memory"):
            self.assertNotIn(unexplained, joined)
        self.assertIn("OPTIONS number", (probe_dir / "predicate_start.txt").read_text(encoding="utf-8"))
        self.assertIn("OPTIONS number", (probe_dir / "role_family.txt").read_text(encoding="utf-8"))

    def test_template_predicate_s_uses_english_normalized_symbol_not_russian_surface(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        sensory = TextSensoryService(core)
        sensory.process("бывают")
        russian_s = core.store.find_symbol_by_form("бывают")
        self.assertIsNotNone(russian_s)

        resolved = TemplateResolver(core, Domain.C).resolve(
            PredicateCandidate(surface="бывают", normalized_hint="be"),
            (ActantRole.SUBJECT, ActantRole.STATE),
        )
        semantic_s = core.store.get_symbol(resolved.template.predicate.uid)
        self.assertEqual(semantic_s.forms, frozenset({"be"}))
        self.assertNotEqual(semantic_s.uid, russian_s.uid)

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
        self.assertIn("OPTIONS:\n0 = none or unclear", prompt)
        self.assertIn("1 = states information as a claim/fact", prompt)
        self.assertIn("\n\nTASK:\n", prompt)
        self.assertTrue(prompt.rstrip().endswith("Reply with one OPTIONS number only."))
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

    def test_parser_failure_policy_empty_preserves_turn_without_semantic_acts(self) -> None:
        class BrokenBackend:
            def generate(self, prompt, *, system="", override=None, role="generic"):
                return LLMResponse("{ definitely truncated", {})

        parser = LLMPerceptionService(
            BrokenBackend(),
            LLMPerceptionSettings(
                protocol="line_v1",
                repair_attempts=1,
                failure_policy="empty",
            ),
        )
        result = parser.parse("привет", InteractionContext())
        self.assertEqual(result.acts_count, 0)
        self.assertTrue(result.diagnostics[0].startswith("PARSER_FAILURE:"))
        diag = parser.diagnostics()[-1]
        self.assertIsNotNone(diag.decoded)
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


if __name__ == "__main__":
    unittest.main()
