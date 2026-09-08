from __future__ import annotations

from pathlib import Path
from dataclasses import replace
from unittest.mock import patch

import pytest

from ah.config import load_config
from ah.llm import LMStudioBackend, LMStudioClient, build_llm_backend
from ah.llm.lmstudio_client import LMStudioClientError

PROJECT = Path(__file__).resolve().parents[1]


def _model(key: str, *, loaded: bool = False, context: int = 16384) -> dict:
    return {
        "type": "llm",
        "key": key,
        "display_name": key,
        "loaded_instances": (
            [{"id": key, "config": {"context_length": context}}] if loaded else []
        ),
    }


def test_lmstudio_config_builds_http_backend_without_local_model_dir():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    assert cfg.llm.backend == "lmstudio"
    assert cfg.llm.lmstudio_base_url == "http://127.0.0.1:1234"
    assert isinstance(build_llm_backend(cfg), LMStudioBackend)
    assert cfg.llm.perception_embedding_model == "text-embedding-nomic-embed-text-v1.5"


def test_lmstudio_start_auto_selects_the_only_loaded_llm():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    cfg = replace(cfg, llm=replace(cfg.llm, lmstudio_model=""))
    backend = LMStudioBackend(cfg)
    models = [_model("first/model"), _model("new/model", loaded=True, context=32768)]
    with patch.object(LMStudioClient, "list_models", return_value=models):
        backend.start()
    assert backend.is_running
    assert backend.status().model_dir == "new/model"
    assert backend.status().context_window == 32768


def test_lmstudio_start_fails_closed_when_multiple_loaded_models_are_ambiguous():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    cfg = replace(cfg, llm=replace(cfg.llm, lmstudio_model=""))
    backend = LMStudioBackend(cfg)
    with patch.object(
        LMStudioClient,
        "list_models",
        return_value=[_model("one", loaded=True), _model("two", loaded=True)],
    ):
        with pytest.raises(RuntimeError, match="Several LM Studio LLMs are loaded"):
            backend.start()
    assert not backend.is_running
    assert backend.status().current_stage == "stopped"


def test_lmstudio_generate_is_stateless_and_strips_think_blocks_from_protocol_calls():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = LMStudioBackend(cfg)
    backend._running = backend._ready = True
    backend._active_model = "new/model"
    captured = {}

    def fake_native_chat(**kwargs):
        captured.update(kwargs)
        return {
            "output": [{"type": "message", "content": "<think>private</think> SUBJECT"}],
            "stats": {"input_tokens": 42, "total_output_tokens": 1, "reasoning_output_tokens": 0},
        }

    with patch.object(backend._client, "native_chat", side_effect=fake_native_chat):
        response = backend.generate(
            "Choose one label.",
            system="Protocol only.",
            role="perception_role_cue",
            override={"max_new_tokens": 8, "temperature": 0.0, "top_p": 1.0, "top_k": 0},
        )

    assert response.text == "SUBJECT"
    assert captured["model"] == "new/model"
    assert captured["prompt"] == "Choose one label."
    assert captured["system"] == "Protocol only."
    assert captured["max_tokens"] == 8
    assert captured["reasoning"] == "off"
    diag = backend.request_diagnostics()[-1]
    assert diag.input_tokens == 42
    assert diag.response_text == "SUBJECT"


def test_lmstudio_client_forces_nonstreaming_openai_chat_completions():
    client = LMStudioClient("http://127.0.0.1:1234/v1")
    captured = {}

    def fake_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {"choices": [{"message": {"content": "OK"}}]}

    with patch.object(client, "_request", side_effect=fake_request):
        client.chat_completions(
            model="model-key",
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            top_p=1.0,
            top_k=0,
            repeat_penalty=1.0,
            max_tokens=4,
        )

    assert captured["method"] == "POST"
    assert captured["path"] == "/v1/chat/completions"
    assert captured["body"]["stream"] is False
    assert client.base_url == "http://127.0.0.1:1234"


def test_lmstudio_embeddings_are_batched_and_ordered_by_response_index():
    client = LMStudioClient("http://127.0.0.1:1234")
    captured = {}

    def fake_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {
            "data": [
                {"index": 1, "embedding": [0, 1]},
                {"index": 0, "embedding": [1, 0]},
            ]
        }

    with patch.object(client, "_request", side_effect=fake_request):
        vectors = client.embeddings(model="embedding-key", texts=("context", "candidate"))

    assert captured == {
        "method": "POST",
        "path": "/v1/embeddings",
        "body": {"model": "embedding-key", "input": ["context", "candidate"]},
    }
    assert vectors == ((1.0, 0.0), (0.0, 1.0))


@pytest.mark.parametrize(
    ("data", "message"),
    (
        (
            {"data": [
                {"index": 0, "embedding": [1, 0]},
                {"index": 0, "embedding": [0, 1]},
            ]},
            "invalid or duplicate indices",
        ),
        (
            {"data": [
                {"index": 0, "embedding": [1, float("nan")]},
                {"index": 1, "embedding": [0, 1]},
            ]},
            "non-finite vector",
        ),
    ),
)
def test_lmstudio_embeddings_reject_malformed_batches(data, message):
    client = LMStudioClient("http://127.0.0.1:1234")
    with patch.object(client, "_request", return_value=data):
        with pytest.raises(LMStudioClientError, match=message):
            client.embeddings(model="embedding-key", texts=("context", "candidate"))


def test_lmstudio_client_discovers_models_via_openai_compatible_endpoint():
    client = LMStudioClient("http://127.0.0.1:1234")
    captured = {}

    def fake_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {
            "object": "list",
            "data": [
                {"id": "publisher/Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF", "object": "model"}
            ],
        }

    with patch.object(client, "_request", side_effect=fake_request):
        models = client.list_models()

    assert captured["method"] == "GET"
    assert captured["path"] == "/v1/models"
    assert models == [{
        "id": "publisher/Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF",
        "object": "model",
        "type": "llm",
        "key": "publisher/Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF",
        "display_name": "publisher/Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF",
        "loaded_instances": [],
        "discovery_api": "openai-compatible",
    }]


def test_lmstudio_configured_name_can_match_unique_model_id_leaf():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = LMStudioBackend(cfg)
    models = [_model("publisher/Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF")]
    selected, _ = backend._select_model(
        "Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF",
        models,
    )
    assert selected == "publisher/Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF"


def test_lmstudio_gguf_display_name_matches_runtime_key_without_packaging_suffix():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = LMStudioBackend(cfg)
    models = [_model("qwen3.8-27b-nvfp4-q5k-no-mtp")]
    selected, _ = backend._select_model(
        "Qwen3.8-27B-NVFP4-Q5K-no-MTP-GGUF",
        models,
    )
    assert selected == "qwen3.8-27b-nvfp4-q5k-no-mtp"


def test_lmstudio_config_uses_actual_qwen38_runtime_key():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    assert cfg.llm.lmstudio_model == "qwen3.8-27b-nvfp4-q5k-no-mtp"


def test_lmstudio_client_requests_thinking_disabled_through_both_compatibility_surfaces():
    client = LMStudioClient("http://127.0.0.1:1234")
    captured = {}

    def fake_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {"choices": [{"message": {"content": "OK"}}]}

    with patch.object(client, "_request", side_effect=fake_request):
        client.chat_completions(
            model="model-key",
            messages=[{"role": "user", "content": "ping"}],
            temperature=0.0,
            top_p=1.0,
            top_k=0,
            repeat_penalty=1.0,
            max_tokens=4,
            enable_thinking=False,
        )

    assert captured["body"]["enable_thinking"] is False
    assert captured["body"]["chat_template_kwargs"] == {"enable_thinking": False}


def test_lmstudio_backend_passes_configured_enable_thinking_false_to_transport():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = LMStudioBackend(cfg)
    backend._running = backend._ready = True
    backend._active_model = "new/model"
    captured = {}

    def fake_native_chat(**kwargs):
        captured.update(kwargs)
        return {
            "output": [{"type": "message", "content": "SUBJECT"}],
            "stats": {"reasoning_output_tokens": 0},
        }

    with patch.object(backend._client, "native_chat", side_effect=fake_native_chat):
        response = backend.generate(
            "Choose one label.",
            system="Protocol only.",
            role="perception_role_cue",
            override={"max_new_tokens": 8},
        )

    assert response.text == "SUBJECT"
    assert captured["reasoning"] == "off"


def test_lmstudio_empty_content_with_reasoning_fails_closed_instead_of_becoming_parser_empty_string():
    data = {
        "choices": [{
            "finish_reason": "length",
            "message": {
                "content": "",
                "reasoning_content": "hidden model reasoning that must not be used as protocol output",
            },
        }],
        "usage": {
            "completion_tokens": 10,
            "completion_tokens_details": {"reasoning_tokens": 10},
        },
    }
    with pytest.raises(LMStudioClientError, match=r"empty assistant content.*reasoning_tokens=10.*reasoning_content=present"):
        LMStudioClient.chat_text(data)


def test_lmstudio_empty_content_without_reasoning_also_fails_closed():
    data = {
        "choices": [{"finish_reason": "stop", "message": {"content": ""}}],
        "usage": {"completion_tokens": 0},
    }
    with pytest.raises(LMStudioClientError, match=r"empty assistant content.*reasoning_content=absent"):
        LMStudioClient.chat_text(data)


def test_lmstudio_native_chat_disables_reasoning_and_storage_for_protocol_probe_transport():
    client = LMStudioClient("http://127.0.0.1:1234")
    captured = {}

    def fake_request(method, path, body=None):
        captured.update({"method": method, "path": path, "body": body})
        return {
            "output": [{"type": "message", "content": "SUBJECT"}],
            "stats": {"input_tokens": 11, "total_output_tokens": 1, "reasoning_output_tokens": 0},
        }

    with patch.object(client, "_request", side_effect=fake_request):
        data = client.native_chat(
            model="model-key",
            prompt="Choose one label.",
            system="Protocol only.",
            temperature=0.0,
            top_p=1.0,
            top_k=0,
            repeat_penalty=1.0,
            max_tokens=8,
            reasoning="off",
        )

    assert captured["method"] == "POST"
    assert captured["path"] == "/api/v1/chat"
    assert captured["body"]["reasoning"] == "off"
    assert captured["body"]["store"] is False
    assert captured["body"]["stream"] is False
    assert captured["body"]["max_output_tokens"] == 8
    assert captured["body"]["system_prompt"] == "Protocol only."
    assert LMStudioClient.native_chat_text(data) == "SUBJECT"


def test_lmstudio_backend_uses_native_reasoning_off_transport_for_bounded_protocol_probes():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = LMStudioBackend(cfg)
    backend._running = backend._ready = True
    backend._active_model = "new/model"
    captured = {}

    def fake_native_chat(**kwargs):
        captured.update(kwargs)
        return {
            "output": [{"type": "message", "content": "SUBJECT"}],
            "stats": {"input_tokens": 42, "total_output_tokens": 1, "reasoning_output_tokens": 0},
        }

    with patch.object(backend._client, "native_chat", side_effect=fake_native_chat), patch.object(
        backend._client, "chat_completions"
    ) as compat:
        response = backend.generate(
            "Choose one label.",
            system="Protocol only.",
            role="perception_role_cue",
            override={"max_new_tokens": 8, "enable_thinking": False},
        )

    assert response.text == "SUBJECT"
    assert captured["model"] == "new/model"
    assert captured["reasoning"] == "off"
    assert captured["max_tokens"] == 8
    compat.assert_not_called()
    diag = backend.request_diagnostics()[-1]
    assert diag.input_tokens == 42
    assert diag.response_text == "SUBJECT"


def test_lmstudio_backend_keeps_openai_compat_transport_for_nonprobe_generation():
    cfg = load_config(PROJECT / "config" / "lmstudio.toml")
    backend = LMStudioBackend(cfg)
    backend._running = backend._ready = True
    backend._active_model = "new/model"
    captured = {}

    def fake_chat_completions(**kwargs):
        captured.update(kwargs)
        return {
            "choices": [{"message": {"content": "ordinary answer"}}],
            "usage": {"prompt_tokens": 7},
        }

    with patch.object(backend._client, "chat_completions", side_effect=fake_chat_completions), patch.object(
        backend._client, "native_chat"
    ) as native:
        response = backend.generate(
            "Answer normally.",
            system="",
            role="agent",
            override={"max_new_tokens": 16, "enable_thinking": False},
        )

    assert response.text == "ordinary answer"
    assert captured["max_tokens"] == 16
    native.assert_not_called()


def test_lmstudio_native_chat_empty_message_with_reasoning_fails_closed():
    data = {
        "output": [{"type": "reasoning", "content": "hidden reasoning only"}],
        "stats": {"total_output_tokens": 8, "reasoning_output_tokens": 8},
    }
    with pytest.raises(
        LMStudioClientError,
        match=r"native chat returned no message content.*reasoning_output_tokens=8.*reasoning_content=present",
    ):
        LMStudioClient.native_chat_text(data)
