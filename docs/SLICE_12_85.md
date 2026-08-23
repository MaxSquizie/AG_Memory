# v0.12.85 — monolithic literary document acceptance

This slice keeps the three strict paragraph-level document scenarios from v0.12.84 and adds one hand-authored literary monolith.

The source monolith is stored as one continuous text. Before perception, diagnostics applies only a deterministic ingestion boundary: explicit sentence splitting and fixed two-sentence windows. No LLM, AH state, causal label, entity identity or oracle data participates in splitting. All windows of one document remain inside one acceptance scenario, so AH, InteractionContext and Ignition state remain continuous.

The production adaptive parser remains bounded (`max_acts=4`). A large document is therefore not silently sent as one giant perception request; doing so would violate the parser's fail-closed resource contract. The ingestion plan is written to `document_ingest_plan.json`, including the untouched source text and every generated perception unit.

The literary monolith is graded primarily by a hand-written final canonical graph oracle. Its individual bounded windows use `perception.unchecked=true`: they must parse successfully, but exact semantic grading is deferred to the final document graph. This diagnostic flag changes no perception/integration behavior and is reusable for document-scale evaluation where duplicating a complete sentence-level oracle would obscure the graph-level objective.

The oracle checks canonical facts, cross-window entity identity, typed CAUSE/FOLLOW links, forbidden causal links, and a six-edge CAUSE chain prepared for later M2 execution.
