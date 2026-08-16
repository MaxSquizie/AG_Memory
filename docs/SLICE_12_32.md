# Slice 12.32 — counterbalanced ordinal semantic cues

## Architecture boundary

Normative flow remains:

```text
unknown predicate
→ Perception TemplateCandidate
→ deterministic validation
→ canonical T registration in Integration
```

Perception never assigns canonical UIDs and never mutates AH. `T` valency evolution
remains `[DEFER]`; an unresolved justified hidden role is therefore fail-closed before
canonical T creation.

## Why the v0.12.31 event labels were removed

The real acceptance run showed a systematic output-label prior: every
`template_event_frame` request selected `TRANSFER_TO_RECEIVER`, including verbs such as
`читать`, `открыть`, `любить` and `победить`. Because incorrect choices had large score
margins, threshold tuning could not separate semantic quality from label prior.

v0.12.32 no longer lets the SLM score semantic class names as output continuations.

## Binary ordinal protocol

Directional discovery uses at most two semantic bits.

First bit:

```text
VERB: <surface>
FIRST: verb normally includes receiver/addressee/destination/source/origin
SECOND: verb normally includes none of these participants

answer: FIRST | SECOND
```

If no directional participant exists, discovery stops. Otherwise a second bit is asked:

```text
FIRST: receiver/addressee/beneficiary/destination
SECOND: source/origin

answer: FIRST | SECOND
```

Python maps the final cue to exactly one hidden `RECIPIENT` or `SOURCE`.

## Swap-and-agree

Each binary question is scored twice with the descriptions reversed:

```text
pass 1: FIRST=X, SECOND=Y
pass 2: FIRST=Y, SECOND=X
```

Answers are mapped back to `X/Y` by deterministic code. Only agreement is accepted.
A low-margin pass or disagreement is explicit ambiguity/error. Thus a pure FIRST-token
or SECOND-token prior cannot create a canonical role.

## Deterministic morphology narrowing

Template discovery also reuses the predicate lexeme already resolved by raw
Perception. Surface homographs belonging to another lexeme are removed before
transitivity consensus. If more than one reading of that lexeme remains, explicit
subject-number agreement can remove grammatically incompatible readings.

For the acceptance sentence:

```text
Иван и Мария пришли и ушли.
```

coordinated nominative `Иван и Мария` deterministically establishes plural agreement.
The singular imperative transitive homographs are discarded, leaving intransitive
`прийти` / `уйти` without an OBJECT SLM probe.

## Preserved mechanisms

- relation-specific CONTENT/GOAL/CAUSE/MANNER probes;
- direct mutually-exclusive controller choice;
- finite-plural omitted-agent grammar;
- full fixed-choice score/margin diagnostics;
- strict existing-T reuse and `[DEFER]` valency evolution;
- `k_AMBIGUOUS` clarification lifecycle;
- live VisPy acceptance canvas.
