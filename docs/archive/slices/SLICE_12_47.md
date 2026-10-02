# Slice v0.12.47 — broad200 semantic corpus

This slice changes diagnostics and acceptance data only. Production Perception,
Integration, inference and AH Core semantics are intentionally unchanged.

## Changes

- Expanded the default semantic acceptance corpus from 40 to 200 sequential cases.
- Preserved the original 40-case suite verbatim in dedicated regression files.
- Added 160 new exact-oracle cases across 16 stress families, including previously
  thinly tested canonical roles (SOURCE/TOOL/MATERIAL/DURATION/AMOUNT/PURPOSE),
  query roles, deeper nested content, personal provenance, conditionals, passive/
  impersonal syntax, ambiguity, and Russian case-syncretism pressure.
- Added optional `family` and `tags` metadata to semantic-oracle cases.
- Live and offline semantic reports now aggregate PASS/FAIL/GAP per family and
  preserve family/tags in turn diagnostics.
- No new case is pre-labelled `ARCHITECTURE_GAP`; all 200 expectations are EXACT.
  The first real broad200 run is expected to reveal failures.

Architecture_v3 remains working specification v0.11 because this slice does not
change product semantics.
