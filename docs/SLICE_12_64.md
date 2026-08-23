# v0.12.64 — clarification isolation and PROVE command execution

This slice fixes the dialogue failure where an unrelated new request could be trapped behind an older unresolved ambiguity and rendered as an opaque `[1]/[2]` clarification.

- Pending clarification no longer monopolizes the next user turn. The current utterance is checked as an explicit clarification answer; if it selects no option, it proceeds through ordinary perception/inference while the unresolved ambiguity remains pending.
- Agent clarification verbalization is validated deterministically. A generated question must contain every user-visible option label; opaque `[1]/[2]`-only wording is rejected and replaced by deterministic clarification text with the real labels.
- Assertion content structurally embedded under non-quoted QUERY/COMMAND roots is marked `EMBEDDED` before canonical integration. Mentioning proposition `P` inside `ask/command(P)` therefore does not assert `P` as a world fact.
- `PROVE` is now a behavioral command executed by the orchestrator (`доказать` / `докажи` / `докажите` / `prove`). Its single embedded positive proposition is converted to a read-only `ExistsGoal`; the embedded target itself is excluded from truth matching, so the request cannot prove itself by mention.
- `UNKNOWN` and `DISPROVED` inference outcomes are now projected to AgentContext as semantic logical results. Internal stop reasons, UID traces and search mechanics remain hidden from the response model.
- Regression coverage includes the independent request `Докажи что Крипл - это ИИ` arriving while an older ambiguity is pending, opaque `[1]/[2]` verbalization, successful PROVE against a pre-existing fact, and UNKNOWN when the only matching proposition is the command's own embedded target.

Validation:
- `419 passed, 1 deselected, 22 subtests passed` for the light suite;
- the deselected 150k M2 operator test passes separately (`1 passed`);
- total regression tests: `420 passed`, `22 subtests passed`;
- M2 operator acceptance: `40/40`, `153502` AH UIDs.
