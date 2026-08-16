# Slice 12.23 — bounded TemplateCandidate discovery

## Problem

v0.12.22 decomposed dynamic `TemplateCandidate` discovery into repeated finite probes.
A weak model biased toward the numeric `YES` continuation could repeatedly request another
hidden role and walk most of the canonical role ontology. The loop was technically finite but
operationally runaway, producing hundreds of LLM requests and an over-broad `T`.

## Architecture alignment

The architecture requires `unknown predicate -> LLM TemplateCandidate -> deterministic
validation -> canonical T`. It does not require exhaustive interrogation of every role.
The parser therefore treats hidden-role expansion as bounded evidence gathering.

## Changes

- The binary `template_more_core` decision is asked twice with swapped numeric labels.
- `YES` is accepted only when both probes agree semantically. Numeric-token bias therefore
  produces disagreement and stops hidden-role expansion conservatively.
- A single template may add at most two hidden roles and spend at most ten real LLM probes.
- If the model still requests additional hidden roles after the bound, Perception fails
  explicitly instead of traversing the remaining ontology or mutating AH with a garbage `T`.
- Observed roles are always preserved; no existing `T` widening/evolution was added.

## Regression coverage

- constant numeric-token `1` bias stops after two counterbalanced probes;
- semantically consistent endless `YES` fails within the hard budget;
- existing reusable-schema test still discovers `RECIPIENT` when the model answers
  counterbalanced probes consistently.
