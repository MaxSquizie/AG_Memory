from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ah.config import load_config, validate_app_config
from ah.llm.factory import build_llm_backend
from ah.llm.ollama_backend import OllamaBackend
from ah.llm.ollama_client import OllamaClient
from ah.llm.process_backend import LocalLLMProcessBackend

PROJECT = Path(__file__).resolve().parents[1]


class OllamaConfigTests(unittest.TestCase):
    def test_ollama_config_loads_without_model_dir(self) -> None:
        cfg = load_config(PROJECT / "config/ollama.toml")
        self.assertEqual(cfg.llm.backend, "ollama")
        self.assertEqual(cfg.llm.ollama_model, "qwen2.5:7b")
        validate_app_config(cfg)

    def test_builtin_config_requires_model_dir_on_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cfg.toml"
            cfg_path.write_text(
                """
[paths]
project_dir = "."
llm_model_dir = ""

[llm]
enabled = true
backend = "builtin_process"
""",
                encoding="utf-8",
            )
            cfg = load_config(cfg_path)
            with self.assertRaisesRegex(ValueError, "llm_model_dir"):
                validate_app_config(cfg)

    def test_ollama_config_requires_model_name_on_validate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "cfg.toml"
            cfg_path.write_text(
                """
[paths]
project_dir = "."

[llm]
enabled = true
backend = "ollama"
ollama_model = ""
""",
                encoding="utf-8",
            )
            cfg = load_config(cfg_path)
            with self.assertRaisesRegex(ValueError, "ollama_model"):
                validate_app_config(cfg)


class OllamaFactoryTests(unittest.TestCase):
    def test_build_llm_backend_selects_implementation(self) -> None:
        ollama_cfg = load_config(PROJECT / "config/ollama.toml")
        builtin_cfg = load_config(PROJECT / "config/default.toml")
        self.assertIsInstance(build_llm_backend(ollama_cfg), OllamaBackend)
        self.assertIsInstance(build_llm_backend(builtin_cfg), LocalLLMProcessBackend)


class OllamaBackendTests(unittest.TestCase):
    def test_choice_scoring_returns_margin(self) -> None:
        cfg = load_config(PROJECT / "config/ollama.toml")
        backend = OllamaBackend(cfg)
        backend._running = True
        backend._ready = True

        def fake_generate(*, model: str, prompt: str, options=None, logprobs: bool = False):
            self.assertTrue(logprobs)
            if "A" in prompt:
                return {"logprobs": [{"logprob": -0.1}, {"logprob": -0.2}]}
            return {"logprobs": [{"logprob": -2.0}]}

        with patch.object(backend._client, "generate", side_effect=fake_generate):
            response = backend.generate(
                "pick",
                system="sys",
                override={
                    "choice_outputs": ["A", "B"],
                    "return_choice_scores": True,
                },
                role="perception",
            )
        self.assertEqual(response.text, "A")
        self.assertIn("choice_margin", response.raw)

    def test_start_checks_model_availability(self) -> None:
        cfg = load_config(PROJECT / "config/ollama.toml")
        backend = OllamaBackend(cfg)
        with patch.object(backend._client, "list_models", return_value=["other:7b"]):
            with self.assertRaisesRegex(RuntimeError, "not available"):
                backend.start()

    def test_perception_roles_disable_thinking(self) -> None:
        cfg = load_config(PROJECT / "config/ollama.toml")
        backend = OllamaBackend(cfg)
        backend._running = True
        backend._ready = True
        captured: dict[str, object] = {}

        def fake_chat(**kwargs):
            captured.update(kwargs)
            return "ACTOR_OR_EXPERIENCER"

        with patch.object(backend._client, "chat", side_effect=fake_chat):
            response = backend.generate("probe", system="sys", role="perception_role_cue")
        self.assertEqual(response.text, "ACTOR_OR_EXPERIENCER")
        self.assertIs(captured.get("think"), False)


class OllamaClientTests(unittest.TestCase):
    def test_list_models_parses_tags(self) -> None:
        client = OllamaClient("http://127.0.0.1:11434")
        payload = json.dumps({"models": [{"name": "qwen2.5:7b"}, {"name": "llama3:latest"}]}).encode()

        class FakeResp:
            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return payload

        with patch("urllib.request.urlopen", return_value=FakeResp()):
            self.assertEqual(client.list_models(), ["llama3:latest", "qwen2.5:7b"])

    def test_chat_passes_think_flag(self) -> None:
        client = OllamaClient("http://127.0.0.1:11434")
        captured: dict[str, object] = {}

        def fake_request(method, path, body=None):
            captured["body"] = body
            return {
                "message": {
                    "role": "assistant",
                    "content": "ACTOR_OR_EXPERIENCER",
                }
            }

        with patch.object(client, "_request", side_effect=fake_request):
            text = client.chat(
                model="gemma4:9b",
                messages=[{"role": "user", "content": "probe"}],
                think=False,
            )
        self.assertEqual(text, "ACTOR_OR_EXPERIENCER")
        self.assertIs(captured["body"]["think"], False)

    def test_chat_falls_back_to_thinking_when_content_empty(self) -> None:
        client = OllamaClient("http://127.0.0.1:11434")

        def fake_request(method, path, body=None):
            return {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "thinking": "AFFECTED_OR_CONTENT",
                }
            }

        with patch.object(client, "_request", side_effect=fake_request):
            self.assertEqual(
                client.chat(
                    model="gemma4:9b",
                    messages=[{"role": "user", "content": "probe"}],
                ),
                "AFFECTED_OR_CONTENT",
            )


if __name__ == "__main__":
    unittest.main()
