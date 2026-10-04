# -*- coding: utf-8 -*-
"""Exercise the open-set path (gate -> bounded probe -> verify) end-to-end.

HONESTY NOTE (important): on current real data with gemma-3n-e4b-it, out-of-set predicates are
FORCE-FIT to the nearest declared value rather than reported as NONE_FIT/NO_CANDIDATE (see the S1-S6
and alien-predicate runs). So genuine honest misses do not yet accumulate and the gate does not fire on
real data. This script therefore feeds a small set of SYNTHETIC NO_CANDIDATE states (clearly labeled) as
stand-ins for the accumulation that would occur once NONE_FIT calibration / a stronger model is in place,
so it can exercise the REAL LLM probe + verification path live. It never auto-applies anything: the result
is only a provisional ValueProposal.

Usage:
    PYTHONPATH=src python scripts/run_open_set_live.py --model gemma-3n-e4b-it --base-url http://127.0.0.1:1234
"""

from __future__ import annotations

import argparse

import types

from ah.llm.lmstudio_client import LMStudioClient
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.open_set_probe import maybe_extend, verify_proposal
from ah.formalizer.state import FormalizationState, Decision


class _LMChatBackend:
    """Minimal product-LLM-contract wrapper over LMStudioClient (``.generate -> .text``)."""

    def __init__(self, client: LMStudioClient, model: str) -> None:
        self._client = client
        self._model = model

    def generate(self, prompt: str, *, system: str = "", role: str = "generic") -> types.SimpleNamespace:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        data = self._client.chat_completions(
            model=self._model, messages=messages, temperature=0.0,
            top_p=1.0, top_k=1, repeat_penalty=1.0, max_tokens=64, enable_thinking=False,
        )
        return types.SimpleNamespace(text=data["choices"][0]["message"]["content"] or "")


def _miss_state(text: str) -> FormalizationState:
    st = FormalizationState.new(text)
    st.decisions["f0|predicate_value"] = Decision(
        slot_id="predicate_value", frame_id="f0",
        candidates=("V1", "V2", "V3", "V4"), selected=(),
        selector_outcome="NONE_FIT", outcome="NO_CANDIDATE",
    )
    return st


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--model", default="gemma-3n-e4b-it")
    ap.add_argument("--base-url", default="http://127.0.0.1:1234")
    args = ap.parse_args()

    client = LMStudioClient(args.base_url, timeout_seconds=90, api_key=None)
    backend = _LMChatBackend(client, args.model)
    selector = RealBackendSelector(backend)

    existing = ["HAVE", "HAS_PART", "LOCATIVE", "LIKE"]

    def show(label, texts):
        states = [_miss_state(t) for t in texts]
        proposal = maybe_extend(states, "predicate_value", selector=selector, existing_values=existing, min_distinct=3)
        ok, reason = verify_proposal(proposal, [s.text for s in states])
        if proposal is None:
            print(f"  {label}: no verified proposal ({reason})")
        else:
            print(f"  {label}: value={proposal.value!r} grounding={proposal.grounding_text!r} verify=({ok},{reason})")

    print("gate fired (>=3 distinct synthetic NO_CANDIDATE). Live probe results:")
    show("POSITIVE (shared predicate 'тает')", ["Снег тает.", "Лёд тает.", "Воск тает."])
    show("HETEROGENEOUS (мelt/boil/burn)   ", ["Снег тает.", "Вода кипит.", "Лампа горит."])
    print("NOTE: nothing auto-applied; schema extension is a separate explicit acceptance act.")
    print("LIMITATION observed live: grounding checks against ANY single miss input, so heterogeneous")
    print("misses can over-generalize (e.g. 'MELTS' from one shared word). A stricter 'grounded in all/most'")
    print("check is a candidate refinement; not applied here.")


if __name__ == "__main__":
    main()
