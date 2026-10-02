# Slice v0.12.43 — semantic cue / canonical role separation

The v0.12.42 real-model acceptance run remained at 34 semantic PASS / 2 FAIL / 4 GAP. Both FAILs had already accepted `CONTENT_LINK`, but the local model returned `NOT_RECIPIENT` for the explicit participant in request constructions. v0.12.42 correctly failed closed and prevented the old OBJECT/PURPOSE corruption.

The remaining probe is now formulated below the AH ontology boundary. The model does not decide the canonical role `RECIPIENT`; it decides the concrete natural-language cue `CONTENT_ADDRESSEE`: whether the already-known child content is directed to the explicit participant as the person being asked, told, advised, instructed, or otherwise addressed. Python maps a positive cue to runtime `ActantRole.RECIPIENT`.

This preserves deterministic narrowing, exact binary protocol, sticky CONTENT semantics, and canonical-write ownership in Integration/AH Core.
