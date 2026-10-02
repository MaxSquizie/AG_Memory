# Slice 12.8

GUI graph refresh regression fix.

- Label ranking now operates in `VisualGraph` index space after node filtering.
- Hidden orphan lexical `S` nodes can no longer leave stale `GraphSnapshot` indices that index past `visual.positions`.
- Label text is resolved by visible UID, keeping text and position arrays aligned.
- Added regression coverage with more hidden lexical `S` nodes than visible graph nodes.
