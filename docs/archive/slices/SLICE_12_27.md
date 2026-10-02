# Slice 12.27 — SLM-first perception probes

## Goal

Keep the LLM/SLM boundary semantically minimal. Deterministic code narrows the problem first; the model only removes a small remaining ambiguity.

## Dynamic T

Unknown-predicate handling no longer asks the model for a full valency schema. `TemplateCandidate` starts from roles already evidenced by the current frame. If a generic latent-core ambiguity remains, Perception performs at most one `perception_template_hidden_role` fixed-choice decision over a tiny English shortlist. The selected role is then mapped and validated deterministically.

No recursive role discovery is allowed. No free-form schema generation is allowed. Circumstantial roles are never added merely because every event can have time/place/cause/purpose/tool/manner. Existing T remains strict and valency evolution remains deferred.

## Prompt language

All service instructions are English. Semantic protocol outputs are short English labels. Numeric output is kept only where the task is literally selecting a numbered token or span. User source text is not translated before Perception.

## Weak-model invariant

A weak model can at worst choose one wrong bounded label. It cannot create an unbounded loop, enumerate the ontology, write AH objects, or generate a partial canonical T directly.
