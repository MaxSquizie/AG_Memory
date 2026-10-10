# -*- coding: utf-8 -*-
"""RealBackendSelector — connect a live local LLM backend to the formalizer's bounded-selection
interface (V7 §14 / WP4.1).

The pipeline consumes ``selector.select(prompt) -> raw JSON string`` (see :mod:`ah.formalizer.fake_selector`
for the deterministic dry run). This adapter wraps ANY product LLM backend — built by
:func:`ah.llm.factory.build_llm_backend` (Ollama / LMStudio / Android NPU / builtin process) — behind that
same one-argument interface, driving it through the logged :class:`~ah.formalizer.provider_adapter.ProviderAdapter`
so every real call is replayable and integrity-checked.

Contract points:
- backend-agnostic: only requires ``backend.generate(prompt, *, system=..., role=...)`` returning an object
  with a ``.text`` attribute (the product's LLMResponse contract). No per-backend code lives here.
- a transport failure raises :class:`~ah.formalizer.fake_selector.ProviderUnavailableError`, which the
  pipeline turns into an honest PROVIDER_UNAVAILABLE miss — deterministic candidates continue; a live-model
  outage never becomes AMBIGUOUS (V7 §0.8).
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from ah.formalizer.fake_selector import ProviderUnavailableError
from ah.formalizer.provider_adapter import BudgetSnapshot, ProviderAdapter

_SYSTEM = (
    "You are a bounded language-protocol worker. Answer ONLY with the strict JSON object described in the prompt. "
    "Use only declared IDs, types and roles. Do not add fields, markdown or explanations. "
    "For selection, never invent relations outside the declared closed candidate set."
)


@dataclass
class RealBackendSelector:
    """One-argument ``select(prompt)`` over a live backend, logged via ProviderAdapter."""

    backend: object
    system: str = _SYSTEM
    role: str = "formalizer"
    run_id: str = "real-backend"
    journal: object = None
    budget: BudgetSnapshot | None = None
    generation_settings: dict = field(default_factory=lambda:{"temperature":0.0,"top_p":1.0,"top_k":0,"max_new_tokens":4096,"enable_thinking":False})
    model_key: str = ""

    def __post_init__(self):
        from .provider_call_log import ProviderCallLog
        from .canonical_ledger import digest
        self._adapter = ProviderAdapter(
            name=type(self.backend).__name__,
            capabilities=frozenset({"select", "propose_local"}),
            log=ProviderCallLog(self.journal),
            model_key=self.model_key or str(getattr(self.backend,"model",type(self.backend).__name__)),
            params_hash=digest({"system":self.system,"role":self.role,"generation":self.generation_settings}),
            transport=self._transport,
            budget=self.budget or BudgetSnapshot(tp_calls=2, lexical_calls=2, max_nodes=64, max_edges=128, max_depth=16, token_limit=32768),
        )

    def _transport(self, prompt: str) -> str:
        resp = self.backend.generate(prompt, system=self.system, role=self.role, override=self.generation_settings)
        return resp if isinstance(resp, str) else getattr(resp, "text", "")

    def start_run(self, run_id):
        self.run_id=run_id
        self._adapter.start_run(run_id)

    def for_run(self, run_id):
        """Share the backend/WAL, keep ordinals and budgets local to this run.

        A clarification or migration may wait on the provider concurrently
        with another observation. Its start_run must not replace the other
        execution's mutable run_id or ordinal counter.
        """
        return replace(self, run_id=run_id)

    def propose_local(self, prompt):
        return self._adapter.propose_local(prompt,self.run_id)

    def select(self, prompt: str) -> str:
        return self._adapter.select(prompt, self.run_id)


def selector_from_config(config, journal=None, *, backend=None):
    """Build a :class:`RealBackendSelector` from an AppConfig via the product factory; ``None`` if LLM is disabled."""
    from ah.llm.factory import build_llm_backend

    backend = backend if backend is not None else build_llm_backend(config)
    if backend is None:
        return None
    model=str(getattr(config.llm,config.llm.backend.lower()+'_model',getattr(config.llm,'model_dir','')))
    return RealBackendSelector(backend, system=_SYSTEM, role="formalizer", journal=journal,model_key=type(backend).__name__+':'+model)


# --------------------------------------------------------------------------- #
# Manual S1–S6 driver (WP4.1): run the real selector over the demo sentences and
# report per-sentence outcome + selection. Used to obtain C3 numbers once a local
# model is reachable; hermetic tests use stub backends instead of this path.
# --------------------------------------------------------------------------- #

_DEMO = {
    "baseline": [
        ("У вороны есть лапки.", ()),
        ("У стола есть ножки.", ()),
        ("У меня есть книга.", ()),
        ("Ворона обладает перьями.", ()),
        ("У вороны лапки.", ()),
        ("Вороны любят червей.", ()),
    ],
    "augmented": [
        ("У вороны есть лапки.", ("Лапки — часть тела этой вороны.",)),
        ("У стола есть ножки.", ("Ножки — часть этого стола.",)),
        ("У меня есть книга.", ()),
        ("Ворона обладает перьями.", ("Перья — часть тела этой вороны.",)),
        ("У вороны лапки.", ()),
        ("Вороны любят червей.", ()),
    ],
}


def run_s1s6(selector, mode: str = "baseline"):
    """Run the six demo sentences through the full Phase 1 vertical with ``selector``.

    Returns a list of ``(sentence, outcome, selected, diagnostics)`` tuples — one per sentence — where
    ``outcome``/``selected`` come from the (single) predicate_value decision and ``diagnostics`` is the
    state's diagnostic code list. This is the C3 measurement surface for a real selector."""
    from ah.formalizer.pipeline import run as _run
    from ah.formalizer.selection_protocol import load_decision_schema

    schema = load_decision_schema()
    report = []
    for text, facts in _DEMO[mode]:
        st = _run(text, schema, selector, context_facts=facts)
        decs = [d for d in st.decisions.values() if d.slot_id == "predicate_value"]
        if decs:
            d = decs[0]
            report.append((text, d.outcome, list(d.selected), sorted({x.code for x in st.diagnostics})))
        else:
            report.append((text, None, [], sorted({x.code for x in st.diagnostics})))
    return report
