# Slice 7.5 — domain-aware manual graph editing

This slice is reconciled against `docs/reference/Архитектура_v3.md`.

## Duplicate semantics

The architecture states that `m` UID is canonical identity and `name` is not an identity key. Entity resolution can therefore yield existing / ambiguity / new. It also allows the same semantics to exist independently across C/P/H, while deduplication is scoped to the target domain.

GUI policy follows that distinction:

- `S` has no C/P/H domain. A case-folded wordform has one canonical S owner. Re-entering an existing wordform reuses S and may add missing forms.
- `m` duplicate checks are domain-aware. The default operator policy reuses exactly one same-domain name candidate to prevent accidental duplicates.
- The operator may explicitly choose `reuse_any_domain` to reuse one matching m UID from another C/P/H domain when identity is meant to be shared, matching the architecture's allowance for cross-domain references to a common identity.
- The operator may explicitly choose `create_new` when a same-name m is a different identity or a deliberate domain-local copy.
- If the selected policy still leaves several equally named candidates, the GUI does not guess identity and aborts before mutation.

## Atomicity

Manual node creation plus optional L is one AHCore copy-on-write transaction. Runtime seed is applied only after commit. This fixes the previous failure mode where an index/link error could be displayed after a canonical record had already been inserted.

## Persistence compatibility repair

0.7.4 could leave duplicate S records if `_index_symbol` rejected the second record after it had already been inserted into the canonical symbol map. 0.7.5 repairs only that legacy invalid state during JSON load:

1. find S components sharing a case-folded wordform;
2. choose a deterministic canonical UID;
3. union their forms;
4. rewrite serialized S references;
5. merge runtime/pending seed state conservatively;
6. rebuild all derived indexes from the repaired canonical payload.

No m/N/domain dedup policy is changed by this migration.

## Links and canvas interaction

`L = <UID, ID, w, (e1*, e2*)>` remains the canonical directed typed relation. The new link manager only composes `AHCore.ensure_link`; it is not a second storage API.

The visual layer now has explicit edge metadata for both canonical L and diagnostic structural edges. Hover/selection is read-only:

- node hover/selection -> node + all immediate incoming/outgoing edges + neighbouring endpoints;
- edge hover/selection -> selected segment + both endpoints;
- clicking a node clears edge selection; clicking an edge clears node selection.

Edge hit-testing is performed in canvas pixel coordinates after projecting node positions through VisPy's visual-to-canvas transform. This UI geometry never enters AH, Workspace, Ignition or Inference.
