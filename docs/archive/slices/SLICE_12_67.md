# v0.12.67 — proof provenance and speech-act evidence boundary

This slice closes two black-box paths observed in the live GUI.

1. A current epistemic turn may not receive a substantive Agent LLM answer when deterministic GoalSpec compilation failed. Such turns fail closed with an explicit `UNRESOLVED / GOAL_NOT_COMPILED` proof snapshot and model-visible inference status.
2. Polar queries use `QueryMode.EXISTS` deterministically. Structural/implicit predicates with several role-compatible templates now request the same bounded UID-free template-sense choice instead of silently producing `template_not_unique`.
3. Dialogue H events preserve top-level pragmatic kinds (`ASSERTION`, `QUERY`, `COMMAND`). Questions and commands remain valid lived experience, but projection labels them as non-factual dialogue context. They are not provenance for world facts.
4. Scoped proposition nodes (`EMBEDDED`, `QUOTED`, `CONDITIONAL`) cannot re-enter `ACTIVE MEMORY` as factual evidence. Their semantic result reaches the Agent only through deterministic inference.
5. The Agent service prompt explicitly states that a current question/request and non-asserting dialogue history are never evidence for the proposition being queried.

Regression contracts cover the exact `Крипл - это ИИ?` path, unresolved fail-closed behavior, Proof Explorer visibility, structural template ambiguity, prior-question projection, and embedded-command self-evidence prevention.
