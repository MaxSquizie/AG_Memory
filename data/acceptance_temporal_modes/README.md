# Occurrence TemporalMode acceptance

This corpus grades occurrence-level `STATE / PROCESS / EVENT / TRANSITION`
formalization. Temporal mode is never a global property of canonical `T`.

- 46 independent EXACT cases.
- 12 STATE, 12 PROCESS, 12 EVENT, five transition operators, four deliberately
  unclassified occurrences and one fail-closed ambiguity case.
- TIME and DURATION observability, perfective deterministic narrowing, bounded
  semantic classification, canonical metadata and transition wrappers are graded.
- Sentences are oracle data only and must never become a production phrase list.

Run it through the ordinary semantic acceptance pipeline with
`data/acceptance_temporal_modes/cases.txt` and
`data/acceptance_temporal_modes/oracle.json`.
