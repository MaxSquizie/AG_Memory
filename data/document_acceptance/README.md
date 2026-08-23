# Document acceptance

The suite contains hand-authored document scenarios and a hand-written oracle.

- `cooling_station`, `greenhouse_control`, `archive_leak`: strict paragraph-by-paragraph semantic oracle plus final canonical graph checks.
- `house_by_pier_monolith`: one continuous literary source text. Diagnostics performs deterministic sentence-boundary ingestion into fixed two-sentence windows because the production perception parser is intentionally bounded by `max_acts`. No semantic decision is made by the splitter. Window runtime must succeed; semantic grading is concentrated in the hand-written final canonical graph oracle.

All units belonging to one document share one acceptance scenario. Therefore canonical AH, `InteractionContext`, and Ignition state persist between units. State is reset only between different documents.

Every run writes `document_ingest_plan.json`, preserving the original source text and the exact units sent to perception, plus `document_report.json`, `document_summary.txt`, and per-document matched canonical fact IDs.
