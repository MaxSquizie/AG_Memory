# -*- coding: utf-8 -*-
"""Run the Phase 1 formalizer vertical against a REAL local model and report C3 (V7 §14 / WP4.1).

C3 = fraction of raw selector responses that are protocol-valid strict JSON (validated by
``validate_selection_response``). This is the live-model measurement surface: it complements the
deterministic FakeSelector dry run by showing how often a real model honors the bounded-selection
protocol on the six demo sentences.

Usage:
    PYTHONPATH=src python scripts/run_formalizer_real_backend.py \
        --model gemma-3n-e4b-it --base-url http://localhost:1234 [--mode baseline|augmented|both]
"""

from __future__ import annotations

import argparse
import types

from ah.llm.lmstudio_client import LMStudioClient
from ah.formalizer.real_backend import RealBackendSelector, run_s1s6
from ah.formalizer.selection_protocol import load_decision_schema, validate_selection_response


class _LMChatBackend:
    """Minimal product-LLM-contract wrapper over LMStudioClient (``.generate -> .text``).

    Captures every raw response so the driver can score C3 independently of pipeline internals."""

    def __init__(self, client: LMStudioClient, model: str) -> None:
        self._client = client
        self._model = model
        self.raw_responses: list[str] = []

    def generate(self, prompt: str, *, system: str = "", role: str = "generic") -> types.SimpleNamespace:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = self._client.chat_completions(
            model=self._model,
            messages=messages,
            temperature=0.0,
            top_p=1.0,
            top_k=1,
            repeat_penalty=1.0,
            max_tokens=64,
            enable_thinking=False,
        )
        text = data["choices"][0]["message"]["content"] or ""
        self.raw_responses.append(text)
        return types.SimpleNamespace(text=text)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--model", default="gemma-3n-e4b-it")
    parser.add_argument("--base-url", default="http://localhost:1234")
    parser.add_argument("--mode", choices=["baseline", "augmented", "both"], default="both")
    args = parser.parse_args()

    client = LMStudioClient(args.base_url, timeout_seconds=90, api_key=None)
    backend = _LMChatBackend(client, args.model)
    selector = RealBackendSelector(backend)
    schema = load_decision_schema()

    modes = ["baseline", "augmented"] if args.mode == "both" else [args.mode]
    for mode in modes:
        print(f"\n=== {mode} (model={args.model}) ===")
        before = len(backend.raw_responses)
        report = run_s1s6(selector, mode)
        for text, outcome, selected, diags in report:
            print(f"  {text!r}\n      outcome={outcome} selected={selected} diag={diags}")
        raws = backend.raw_responses[before:]
        valid = sum(1 for r in raws if _valid(r, schema))
        print(f"  C3: {valid}/{len(raws)} protocol-valid responses")


def _valid(raw: str, schema) -> bool:
    try:
        validate_selection_response(raw, schema)
        return True
    except Exception:
        return False


if __name__ == "__main__":
    main()
