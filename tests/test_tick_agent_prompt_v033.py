from __future__ import annotations

from collections import deque
from pathlib import Path
from threading import Lock
import unittest

from ah.config import IgnitionSettings, load_config
from ah.llm.process_backend import LocalLLMProcessBackend
from ah.llm.worker import _render_prompt_for_diagnostics


class _FakeTokenizer:
    def apply_chat_template(
        self,
        messages,
        *,
        tokenize=False,
        add_generation_prompt=True,
        enable_thinking=False,
        **_kwargs,
    ):
        if tokenize:
            raise AssertionError("diagnostic renderer must request text")
        body = "".join(f"<{m['role']}>{m['content']}</{m['role']}>" for m in messages)
        return body + ("<assistant>" if add_generation_prompt else "") + (
            "<thinking-enabled>" if enable_thinking else ""
        )


class TickAndAgentPromptV033Tests(unittest.TestCase):
    def test_mvp_default_tick_is_one_second(self):
        self.assertEqual(IgnitionSettings().tick_interval_seconds, 1.0)
        cfg = load_config(Path(__file__).parents[1] / "config" / "default.toml")
        self.assertEqual(cfg.ignition.tick_interval_seconds, 1.0)

    def test_agent_diagnostic_renderer_contains_system_context_and_generation_marker(self):
        rendered = _render_prompt_for_diagnostics(
            {"tokenizer": _FakeTokenizer(), "enable_thinking": False},
            "SYSTEM RULES",
            "CURRENT INPUT + ACTIVE MEMORY",
        )
        self.assertIn("<system>SYSTEM RULES</system>", rendered)
        self.assertIn("<user>CURRENT INPUT + ACTIVE MEMORY</user>", rendered)
        self.assertTrue(rendered.endswith("<assistant>"))

    def test_request_diagnostic_keeps_exact_rendered_agent_prompt(self):
        backend = object.__new__(LocalLLMProcessBackend)
        backend._status_lock = Lock()
        backend._request_count = 7
        backend._request_diagnostics = deque(maxlen=50)
        backend._recent_log = deque(maxlen=200)
        backend._record_request(
            req_id="agent-7",
            role="agent",
            prompt="AGENT CONTEXT",
            system="SYSTEM",
            response_text="reply",
            response_meta={
                "rendered_prompt": "<system>SYSTEM</system><user>AGENT CONTEXT</user><assistant>",
                "input_tokens": 123,
            },
        )
        record = backend.request_diagnostics()[0]
        self.assertEqual(record.input_tokens, 123)
        self.assertEqual(
            record.rendered_prompt,
            "<system>SYSTEM</system><user>AGENT CONTEXT</user><assistant>",
        )


if __name__ == "__main__":
    unittest.main()
