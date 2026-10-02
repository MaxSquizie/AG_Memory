# Slice 12.94 — morphology boundary normalization

## Live failure signature

The v0.12.93 document run (`20260823_204830_+0300`) completed all 98 semantic paragraph checks but reported seven runtime errors. Every traceback terminated in `EntityResolver._filter_by_grammatical_number` with:

```text
ValueError: '' is not a valid grammeme for this attribute. Valid grammemes: plur, sing
```

The affected turns were distributed across all three literary scenarios, including plural letters, coordinated predicates, multi-clause prose, and Belyaev's `стал подниматься`. The common cause was therefore below literary parsing.

## Root cause

`Pymorphy3Morphology` declared the public `MorphInfo` fields as `str | None` but assigned pymorphy tag scalars directly:

```python
number=getattr(tag, "number", None)
```

Those values are grammeme objects with string-like rendering but non-standard comparison semantics. They survived through `ActantCandidate.grammatical_number` into Integration. Comparing a normal empty-string fallback with the grammeme object invoked the grammeme's reverse equality and raised.

This violated the adapter boundary: external morphology implementation types must not escape into perception contracts or canonical memory code.

## Fix

The pymorphy adapter now converts all scalar tag attributes to exact built-in strings (`POS`, `case`, `number`, `gender`, `mood`, `animacy`) as soon as a `MorphInfo` is created. Grammatical-number normalization is repeated defensively in the source-span extractor, the `ActantCandidate` invariant, and EntityResolver for legacy/in-memory values.

The fix does **not** remove grammatical-number identity. Singular/plural separation introduced in v0.12.93 remains authoritative; only the runtime representation is normalized.

## Tests

A dependency-free fake grammeme scalar intentionally overloads equality and raises on invalid comparison values. New tests prove:

1. the pymorphy adapter emits only exact Python strings;
2. `ActantCandidate` normalizes a non-plain string scalar;
3. EntityResolver safely compares legacy grammeme metadata.

Full regression:

```text
563 passed
22 subtests passed
compileall OK
```

No document oracle or semantic expectation was changed in this slice.
