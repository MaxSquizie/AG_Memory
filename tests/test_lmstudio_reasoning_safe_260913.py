from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from ah.config import load_config
from ah.llm import build_llm_backend
from ah.llm.reasoning_safe_lmstudio import LMStudioBackend as ReasoningSafeLMStudioBackend


PROJECT = Path(__file__).resolve().parents[1]


def _backend():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = build_llm_backend(cfg)
    assert isinstance(backend, ReasoningSafeLMStudioBackend)
    backend._running = backend._ready = True
    backend._active_model = "new/model"
    return backend


def test_final_agent_thinking_off_uses_native_reasoning_off_without_token_rewrite():
    backend = _backend()
    captured = {}

    def fake_native_chat(**kwargs):
        captured.update(kwargs)
        return {
            "output": [{"type": "message", "content": "visible answer"}],
            "stats": {
                "input_tokens": 17,
                "total_output_tokens": 3,
                "reasoning_output_tokens": 0,
            },
        }

    with patch.object(
        backend._client, "native_chat", side_effect=fake_native_chat
    ), patch.object(backend._client, "chat_completions") as compat:
        response = backend.generate(
            "Answer from grounded context.",
            role="agent",
            override={"max_new_tokens": 384, "enable_thinking": False},
        )

    assert response.text == "visible answer"
    assert captured["reasoning"] == "off"
    assert captured["max_tokens"] == 384
    compat.assert_not_called()
    diagnostic = backend.request_diagnostics()[-1]
    assert diagnostic.role == "agent"
    assert diagnostic.input_tokens == 17


def test_explicit_agent_thinking_true_retains_compatibility_transport():
    backend = _backend()
    captured = {}

    def fake_chat_completions(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": "answer after reasoning"}}],
            "usage": {"prompt_tokens": 9},
        }

    with patch.object(
        backend._client, "chat_completions", side_effect=fake_chat_completions
    ), patch.object(backend._client, "native_chat") as native:
        response = backend.generate(
            "Answer normally.",
            role="agent",
            override={"max_new_tokens": 384, "enable_thinking": True},
        )

    assert response.text == "answer after reasoning"
    assert captured["enable_thinking"] is True
    assert captured["max_tokens"] == 384
    native.assert_not_called()


def test_bounded_probe_and_agent_share_reasoning_off_contract_but_keep_own_budgets():
    backend = _backend()
    budgets = []

    def fake_native_chat(**kwargs):
        budgets.append((kwargs["max_tokens"], kwargs["reasoning"]))
        return {
            "output": [{"type": "message", "content": "C1"}],
            "stats": {"reasoning_output_tokens": 0},
        }

    with patch.object(backend._client, "native_chat", side_effect=fake_native_chat):
        backend.generate(
            "Choose C1 or UNKNOWN.",
            role="lexical_recovery_choice",
            override={"max_new_tokens": 4, "enable_thinking": False},
        )
        backend.generate(
            "Write final answer.",
            role="agent",
            override={"max_new_tokens": 384, "enable_thinking": False},
        )

    assert budgets == [(4, "off"), (384, "off")]
