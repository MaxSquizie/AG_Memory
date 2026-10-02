# Slice 12.12

File-driven black-box acceptance diagnostics for the existing cognitive runtime.

## Goal

Exercise real sequential GUI/orchestrator turns while preserving enough evidence to
locate a failure at the linguistic, perception, integration, inference or canonical
AH boundary. This slice is diagnostics only and does not alter semantic behavior.

## Replaceable cases file

`data/acceptance_cases.txt` is the only suite definition:

```text
# comments are ignored
Первый запрос.
Второй запрос?
```

Rules:

- one user request per non-empty line;
- lines beginning with `#` are comments;
- no expected answers, UIDs or parser metadata are embedded in the file;
- requests execute in source order in one live AH/context session;
- replacing the file contents is sufficient to define another suite.

The bundled suite contains 40 requests covering basic frames, predicate/actant
coordination, coreference, `T/N` reuse and `FILL_ROLE`, nested situations, relative
clauses, temporal/causal/conditional composition, negation/passive forms and
intentional ambiguity pressure.

## GUI

The Dialogue dock contains `Прогнать acceptance-файл`.

Requirements before start:

- local LLM is already running;
- no ordinary chat turn or LLM lifecycle operation is in progress.

While the suite owns the shared runtime, ordinary send and mutating runtime controls
are disabled. The current Ignition state itself is not changed by the runner.

## Output

Every run creates:

```text
data/acceptance_runs/<timestamp>/
  cases_used.txt
  config.json
  initial_context.json
  initial_ah.json
  initial_runtime.json
  turn_001.json
  ...
  final_context.json
  final_ah.json
  final_graph.json
  manifest.json
  summary.txt
```

`data/acceptance_runs/latest.txt` points to the newest run directory.

Every `turn_NNN.json` contains:

```text
input
status
LinguisticCandidateGraph
PerceptionResult / TemplateCandidate
IntegrationCommit
query + inference/materialization output
AgentContext
agent response
response H integration
parser probe diagnostics
raw LLM request diagnostics
canonical AH diff
runtime / Workspace summary
InteractionContext after the turn
traceback on error
```

`TemplateCandidate` is not duplicated into a new diagnostic model; it is exported
from the real `PredicateCandidate` contract inside `PerceptionResult`.

## Strict failure policy

The runner is not a fallback layer.

```text
real turn succeeds -> record exact result
real turn fails    -> record exact exception/traceback and continue with next user turn
```

It never repairs, retries, substitutes an empty semantic result, changes the LLM
answer, creates synthetic canonical facts or bypasses the normal orchestrator. A
`PerceptionParseError` therefore has the same semantics as in ordinary GUI use: only
the raw external H experience may have been recorded by the orchestrator.

## AH diff

Canonical snapshots are generated through public AH reads. Per-turn diff explicitly
records added, removed and changed `S/m/g/k/T/N/L` records, including `T.roles`,
`N.actants`, properties/meta and associative weights. This makes `T != N` regressions
and accidental duplicate canonical structures visible without inspecting the GUI
canvas manually.
