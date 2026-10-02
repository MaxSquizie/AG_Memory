# Slice 12.5 — temporal direction and explicit local coreference

- Compound temporal connectives preserve their own directional meaning instead of collapsing to a generic `TIME=@child` attachment.
- `после того, как`: child situation `FOLLOW` parent situation.
- `до того, как` / `перед тем, как`: parent situation `FOLLOW` child situation.
- `когда` remains a non-directional `TIME` attachment and does not invent `FOLLOW`.
- `PerceptionResult.relations` carries runtime `SituationRelationCandidate` values; Integration validates local endpoints and materializes supported `FOLLOW` candidates as canonical `L`.
- `ActantCandidate.entity_ref` is a turn-local entity-coreference label, distinct from `candidate_ref` (which references another assertion/situation). Integration resolves the first mention once and reuses the exact same canonical entity ref for subsequent coreferent actants.
- Relative-clause antecedents now assign the same `entity_ref` to the parent entity and the rebound child actant.
- Omitted-subject inheritance also preserves exact entity identity through `entity_ref`.
- Prepositional actants keep the complete source phrase in `evidence`, while the semantic mention excludes the relation-bearing preposition. A single nominal complement also gets a morphology-derived `normalized_hint` (`от Ивана` -> mention `Ивана`, normalized `Иван`).
- Assertion evidence is clause-local rather than always spanning the whole source sentence.
- No new LLM probes or examples were added.
