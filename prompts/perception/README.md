# Adaptive perception probes v2

The local LLM is treated as a weak semantic recognizer, not as an AH-aware component.
It never receives UIDs, AH graph state, T/N structures, domain rules, or a serialization grammar.

Python performs tokenization, enumerates legal choices, validates every answer, assembles spans,
maps numeric choices to canonical `ActantRole`, and constructs `PerceptionResult`.

Most probes return **one integer from an explicit OPTIONS list**. No unexplained `N`, `N-M`,
`ROLE`, or other meta-notation is used. The only open-text probe is `predicate_symbol`, because
an unseen Russian predicate still needs a short English semantic name for the predicate `S` used by `T`.

Invalid probes are retried from the same clean input. The previous bad model answer is never shown back to the model.
