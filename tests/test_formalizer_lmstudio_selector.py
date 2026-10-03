# -*- coding: utf-8 -*-
"""Hermetic tests for the LM Studio selector adapter (no network).

The adapter is the real-backend half of the pipeline's backend-agnostic ``select(prompt) -> raw JSON``
contract. These tests monkeypatch the low-level ``_request`` so they run offline and pin down the response
parsing: content extraction, the reasoning fallback, the no-choices error, and model discovery."""

import unittest

from ah.formalizer.lmstudio_selector import LMStudioSelector, LMStudioSelectorError


class TestLMStudioSelector(unittest.TestCase):
    def _sel(self) -> LMStudioSelector:
        return LMStudioSelector(base_url="http://127.0.0.1:1234/", model="gemma-3n-e4b-it")

    def test_select_returns_stripped_content(self):
        sel = self._sel()
        sel._request = lambda method, path, body=None: {  # noqa: ARG005 - canned response
            "choices": [{"message": {"content": "  {\"outcome\": \"ONE_SELECTED\", \"selected\": [\"V1\"]}  "}}]
        }
        self.assertEqual(sel.select("prompt"), '{"outcome": "ONE_SELECTED", "selected": ["V1"]}')

    def test_select_falls_back_to_reasoning_content(self):
        sel = self._sel()
        sel._request = lambda method, path, body=None: {  # noqa: ARG005
            "choices": [{"message": {"content": ""}, "reasoning_content": '{"outcome":"NONE_FIT"}'}]
        }
        self.assertEqual(sel.select("p"), '{"outcome":"NONE_FIT"}')

    def test_select_raises_when_no_choices(self):
        sel = self._sel()
        sel._request = lambda method, path, body=None: {"choices": []}  # noqa: ARG005
        with self.assertRaises(LMStudioSelectorError):
            sel.select("p")

    def test_list_models_maps_ids(self):
        sel = self._sel()
        sel._request = lambda method, path, body=None: {  # noqa: ARG005
            "data": [{"id": "gemma-3n-e4b-it"}, {"id": "qwen2.5-32b-instruct"}]
        }
        self.assertEqual(sel.list_models(), ["gemma-3n-e4b-it", "qwen2.5-32b-instruct"])

    def test_select_sends_stateless_low_temp_request(self):
        sel = self._sel()
        captured: dict = {}

        def fake(method, path, body=None):
            captured["method"], captured["path"], captured["body"] = method, path, body
            return {"choices": [{"message": {"content": "{}"}}]}

        sel._request = fake
        sel.select("hello")
        self.assertEqual(captured["method"], "POST")
        self.assertEqual(captured["path"], "/v1/chat/completions")
        self.assertFalse(captured["body"]["stream"])  # stateless, non-streaming
        self.assertEqual(captured["body"]["model"], "gemma-3n-e4b-it")
        self.assertEqual(captured["body"]["messages"], [{"role": "user", "content": "hello"}])


if __name__ == "__main__":
    unittest.main()
