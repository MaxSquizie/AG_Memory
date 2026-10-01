# -*- coding: utf-8 -*-
"""Phase 1 pipeline T0-T4 (V4 freeze rev2-8) — the mechanism, without an LLM.

T0 tokenize -> T1 morphology/lexicon (whole variants; derived case index) ->
T2 structure (declared finite grammar OP1-OP5; word order ranks but never excludes) ->
T3 bounded selection (PROVISIONAL only; candidates from the schema's declared rule;
one budget charge per attempt; recorded I/O on the decision) ->
T4 joint validation (the ONLY place a semantic outcome is granted).

V5 rev16 stages added (frozen for Phase 1 validation):
- SRL between T0 and T1: deterministic declared patterns ONLY, run through a declarative
  RuleRegistry (rules.py): the core is a generic evaluator with NO language knowledge;
  L1 double-letter orthographic hypothesis, B1 new-predicative-center boundary candidates,
  E1 predicate-gap are RULE DECLARATIONS — adding a pattern = register(), never a change
  to the evaluation loop. SRL proposes structural HYPOTHESES with pattern provenance; it
  creates no ReferenceCandidate, no identity links, no memory facts, no final structure (I24/I26).
- T1 CONSUMES the SRL output [H1]: hypotheses extend LexDecision candidates;
  surviving ClauseCandidates become linked alternatives + a BOUNDARY decision (I29).
- TD (ReferenceResolver §15.4) [H2] — not SRL — creates ReferenceCandidates through four
  DECLARED evidence channels {morphology, syntax, discourse, memory}: the morphology channel
  is a hard agreement filter on R1 features (rejected candidates are RECORDED with a D-trace,
  never deleted silently); syntax/discourse rank observed mentions by the declared
  CoreferencePolicy; memory adds journal-window mentions as W-channel evidence.
  'mention = antecedent' exists only inside a reference DECISION, never before resolution.
- T2 valency check: an unfilled role yields a MissingArgumentCandidate in state
  POSSIBLE_GAP (three-state machine POSSIBLE_GAP/CONFIRMED_GAP/NO_GAP — not binary) [H3];
  every structural object carries ResourceProvenance (pattern_ids + resource_versions).
- I30: after TD+T2 the structural set is CLOSED; EVERY structural producer (SRL/T1/TD/T2)
  raises if called after closure, and T3/T4 only decide over existing objects.
- Traceability (§18.2/I23): trace_decision() reconstructs RawInput -> SRL candidates ->
  FrameCandidate -> Decision for any decision; rejected_alternatives() returns the I29
  audit trail (a candidate leaves the active set ONLY via a recorded RejectionRecord).
  SemanticGraphCandidate/Canonical Memory are Phase 2 objects — in Phase 1 the chain
  legitimately ends at the Decision (I25: nothing writes before the commit stage).

rev8 contracts implemented here:
- T3 candidates come from ``candidates_for_slot`` (schema rule), never hardcoded;
  the validator checks against THIS decision's closed set.
- A failed or successful probe charges the budget exactly ONCE per attempt.
- The M ground for ONE_SELECTED is bound to that value; a MULTIPLE_ADMISSIBLE trace
  is slot-level and grounds no individual value. Slot-level grounds (value=None)
  license the slot but never ground an individual candidate — T4 grounding is
  VALUE-SPECIFIC only.
- T4 cluster validity is real: selected values must lie in the decision's candidates,
  match the slot's declared arity, and respect declared ConstraintEdges.
- Oscillation = returning to a PRIOR state (value + content-based real-ground
  signature) after having left it. A repeat of the same value with unchanged grounds
  is idempotent re-confirmation, not oscillation. New R/C/D/A CONTENT re-arms.
- bounded_search saves its traversal position; a continuation does not re-pay steps.
- Non-FLAT frames (OP4/OP5) are declared stubs: T3 records STRUCTURE_NOT_COVERED
  instead of skipping them silently.

The selector is injected (FakeSelector in the dry run; an LMStudio/Ollama adapter
later). It sees only the prompt — it cannot peek at pipeline state.
"""
from __future__ import annotations

import re
from dataclasses import replace

from ah.formalizer.selection_protocol import (
    ProtocolError,
    build_selection_prompt,
    candidates_for_slot,
    validate_selection_response,
)
from ah.formalizer.rules import RuleRegistry, default_registry
from ah.formalizer.seal import structural_seal
from ah.formalizer.state import (
    BoundaryCandidate,
    Budget,
    ClauseCandidate,
    ConstraintEdge,
    Decision,
    Diagnostic,
    EllipsisCandidate,
    FormalizationState,
    FrameCandidate,
    Ground,
    LinkedAlternative,
    MissingArgumentCandidate,
    MorphVariant,
    ReferenceCandidate,
    ResourceProvenance,
    TokenEvidence,
    TokenHypothesis,
    real_ground_signature,
)

# --------------------------------------------------------------------------- T0


_EDGE_PUNCT = "\u201c\u201d\u201e\u201f\"'.,!?;:()[]"


def t0(text: str) -> FormalizationState:
    state = FormalizationState.new(text)
    for token in re.findall(r"\S+", text):
        span = token.strip(_EDGE_PUNCT)  # terminal punctuation is not part of the word form
        if span:
            state.evidence.append(TokenEvidence(span=span))
    return state


# --------------------------------------------------------------------------- SRL + T1


# --------------------------------------------------------------------------- SRL (V5 §17)
# Structural Reconstruction Layer. The core below is a GENERIC EVALUATOR with no
# language knowledge: it runs the registered StructuralRules in declared order and
# collects their candidates. All pattern knowledge lives in rules.py declarations;
# adding a pattern = registry.register(rule) — this loop never changes (CP1/I13).

_GRAMMAR_VERSION = "op1-op5-v1"


def _parses(provider: MorphProvider, span: str) -> tuple:
    return provider.analyze(span)


def srl(
    state: FormalizationState,
    morph: MorphProvider | None = None,
    registry: RuleRegistry | None = None,
) -> FormalizationState:
    """SRL stage (lifecycle T0 -> SRL -> T1). Creates structural hypotheses ONLY.

    Generic evaluation over the declared ruleset (default_registry(): L1/B1/E1).
    Nothing here creates ReferenceCandidates, identity links, memory facts or final
    ClauseUnit/Frame decisions (I24/I26); every produced object carries its rule's
    pattern provenance (I27)."""
    state.require_structures_open("SRL")
    reg = registry or default_registry()
    provider = morph or MorphProvider()
    evs = state.evidence
    n = len(evs)
    parses = [_parses(provider, ev.span) for ev in evs]

    # Generic loop: declared rules only; the core knows no pattern and no word.
    for rule in reg.rules:
        if not rule.activate(evs, parses):
            continue
        for obj in rule.produce(state, evs, parses):
            if isinstance(obj, TokenHypothesis):
                state.token_hypotheses.append(obj)
            elif isinstance(obj, BoundaryCandidate):
                state.boundary_candidates.append(obj)
            elif isinstance(obj, EllipsisCandidate):
                state.ellipsis_candidates.append(obj)

    # Bookkeeping over fired boundaries (not language knowledge): the no-boundary
    # default plus one segmentation per declared boundary candidate.
    state.clause_candidates.append(ClauseCandidate(
        candidate_id="S0", segmentation=((0, n - 1),),
        provenance=ResourceProvenance(pattern_ids=("B0_no_boundary",)),
    ))
    for bc in state.boundary_candidates:
        seg = ((0, bc.position - 1), (bc.position, n - 1)) if bc.position > 0 else ((bc.position, n - 1),)
        state.clause_candidates.append(ClauseCandidate(
            candidate_id=f"S{bc.candidate_id}", segmentation=seg, provenance=bc.provenance,
        ))
    return state


# --------------------------------------------------------------------------- T1


class MorphProvider:
    """R1 output contract (rev7/rev8): WHOLE dictionary parses. Each variant keeps its
    linked features together — lemma, POS, the parse's own case set, number/gender/
    person/tense/mood and the remaining tagset/dictionary codes (e.g. SUBX). No silent
    score cutoff: every parse is kept; ``score`` only ranks."""

    _CASE_MAP = {
        "nomn": "nom", "gent": "gen", "datv": "dat", "accs": "acc",
        "ablt": "abl", "inst": "ins", "loct": "loc", "vocn": "voc",
    }
    _NUM = {"sing": "sing", "plur": "plur"}
    _GEND = {"masc": "masc", "femn": "femn", "neut": "neut"}
    _PERS = {"1per": "1st", "2per": "2nd", "3per": "3rd"}
    _TENSE = {"past": "past", "pres": "present", "futr": "future"}
    _MOOD = {"indc": "indicative", "impv": "imperative"}

    def __init__(self):
        from pymorphy3 import MorphAnalyzer

        self._morph = MorphAnalyzer()

    def analyze(self, token: str) -> tuple[MorphVariant, ...]:
        out: list[MorphVariant] = []
        for p in self._morph.parse(token):
            tag = p.tag
            grams = set(tag.grammemes)
            cases = frozenset(code for g in grams if (code := self._CASE_MAP.get(g)))
            consumed = {g for g in grams if self._CASE_MAP.get(g)}
            consumed |= {g for g in grams if self._NUM.get(g)}
            consumed |= {g for g in grams if self._GEND.get(g)}
            consumed |= {g for g in grams if self._PERS.get(g)}
            consumed |= {g for g in grams if self._TENSE.get(g)}
            consumed |= {g for g in grams if self._MOOD.get(g)}
            out.append(MorphVariant(
                lemma=p.normal_form,
                pos=tag.POS or None,
                cases=cases,
                number=next((self._NUM[g] for g in sorted(grams) if g in self._NUM), None),
                gender=next((self._GEND[g] for g in sorted(grams) if g in self._GEND), None),
                person=next((self._PERS[g] for g in sorted(grams) if g in self._PERS), None),
                tense=next((self._TENSE[g] for g in sorted(grams) if g in self._TENSE), None),
                mood=next((self._MOOD[g] for g in sorted(grams) if g in self._MOOD), None),
                features=frozenset(grams - consumed),  # SUBX, ASPT, VOCL, ... stay visible
                score=p.score,
            ))
        return tuple(out)


def _expand_shared_form(v: MorphVariant, token: str) -> MorphVariant:
    """Declared shared-form rule (rev8): a NOUN in -ами/-ями whose parse is case-tagged
    abl or ins is ambiguous between them. The correction is applied to the VARIANT's own
    case set — the derived index never gains an entry without variant support."""
    if v.pos == "NOUN" and token.lower().endswith(("ами", "ями")) and (v.cases & {"abl", "ins"}):
        return replace(v, cases=v.cases | {"abl", "ins"})
    return v


def t1(state: FormalizationState, morph: MorphProvider | None = None) -> FormalizationState:
    state.require_structures_open("T1")  # I30: T1 consumes SRL output; it is a structural producer
    provider = morph or MorphProvider()
    for ev in state.evidence:
        variants = tuple(_expand_shared_form(v, ev.span) for v in provider.analyze(ev.span))
        if not variants:
            # OOV is a first-class candidate (keep-as-is), not an error. Dictionary
            # distance may rank candidates later; it never proves a correction.
            ev.lex_status = "OOV_KEEP_AS_IS"
            state.diag("OOV_KEEP_AS_IS", f"'{ev.span}' kept as-is (first-class candidate)")
            lex = Decision(slot_id="lex", frame_id=ev.span, candidates=("keep_as_is",))
            lex.selected = ("keep_as_is",)  # PROVISIONAL pick; a decision, not an error
            lex.lifecycle = "PROVISIONAL"
            lex.grounds.append(Ground(
                "D",
                f"'{ev.span}' kept as-is: first-class candidate; dictionary distance may rank but never prove a correction",
            ))
            state.decisions[f"lex|{ev.span}"] = lex
            continue
        top = max(variants, key=lambda v: v.score)
        ev.variants = variants  # whole parses; nothing dropped by a score cutoff
        ev.lemma, ev.pos, ev.score = top.lemma, top.pos, top.score
        union: frozenset[str] = frozenset()
        for v in variants:  # the index is a STRICT derivation over the variants
            union |= v.cases
        ev.cases = union

    # SRL consumption [Rev16/H1]: hypotheses extend the LexDecision candidate set
    # (keep-as-is stays first-class); surviving ClauseCandidates become linked
    # alternatives and a BOUNDARY decision — nothing is discarded silently (I29).
    for hyp in state.token_hypotheses:
        key = f"lex|{hyp.span_ref}"
        extra = tuple(v for v in hyp.variants if v != "keep_as_is")
        if not extra:
            continue
        dec = state.decisions.get(key)
        if dec is None:
            # L1 flagged an orthographic anomaly on a token that HAS dictionary parses
            # (the form still resolves in the dictionary): it becomes a LexDecision
            # anyway — keep-as-is first-class, PROVISIONAL pick; distance may rank but never prove.
            dec = Decision(slot_id="lex", frame_id=hyp.span_ref, candidates=("keep_as_is", *extra))
            dec.selected = ("keep_as_is",)
            dec.lifecycle = "PROVISIONAL"
            dec.grounds.append(Ground(
                "D",
                f"'{hyp.span_ref}' kept as-is: L1 orthographic hypothesis; dictionary distance may rank but never prove a correction",
            ))
            state.decisions[key] = dec
        else:
            dec.candidates = ("keep_as_is", *extra)
    survivors = state.clause_candidates  # Phase 1: no constraint rejects any yet — all survive
    for cc in survivors:
        state.linked_alternatives.append(LinkedAlternative(
            alt_id=f"alt-{cc.candidate_id}", kind="CLAUSE_SEGMENTATION",
            description=str(cc.segmentation), source_candidate_id=cc.candidate_id,
            provenance=cc.provenance,
        ))
    if len(survivors) > 1:
        dec = Decision(
            slot_id="boundary", frame_id=f"unit:{state.source_uid}",
            candidates=tuple(c.candidate_id for c in survivors),
            provenance=ResourceProvenance(pattern_ids=("B0_no_boundary", "B1_new_predicative_center")),
        )
        state.decisions[f"boundary|unit:{state.source_uid}"] = dec
    return state


# --------------------------------------------------------------------------- T2

_PREP_U = "у"
_COPULAS = {"есть", "нет"}
_CONJUNCTIONS = {"и", "а", "но"}


def _is_copula(ev: TokenEvidence) -> bool:
    """Declared copula test (rev8): lemma in {есть, нет} AND at least one VERB/INFN parse.
    pymorphy3 tags 'есть' top-scored as INFN, so POS alone would miss it."""
    if (ev.lemma or "").lower() not in _COPULAS:
        return False
    return any(v.pos in ("VERB", "INFN") for v in ev.variants)


def _is_possessor(ev: TokenEvidence, prev: TokenEvidence | None) -> bool:
    """OP2 ellipsis condition (declared structural rule): a genitive mention governed by
    'у' is read as possessor. NPRO counts ('у меня'): pronoun case lives in the same
    derived index."""
    if not ev.cases or "gen" not in ev.cases:
        return False
    if prev is None:
        return False
    if prev.pos == "PREP" and (prev.lemma or "").lower() == _PREP_U:
        return True
    # 'у' may be fused into the token; check the raw form as a last resort
    return ev.span.lower().startswith(_PREP_U + "-")


def t2(state: FormalizationState) -> FormalizationState:
    """OP1-OP3 (declared finite grammar, rev7). Word order RANKS candidates but never
    EXCLUDES them: an inverted surface order yields the same candidate space.

    OP4/OP5 (NESTED/COORD) are declared stubs for Phase 2; T3 records
    STRUCTURE_NOT_COVERED for any frame of those kinds instead of skipping silently."""
    state.require_structures_open("T2")  # I30: after closure no stage may add structure
    evs = state.evidence
    frames: list[FrameCandidate] = []
    n = len(evs)

    def nominal(i: int) -> bool:
        return (evs[i].pos in ("NOUN", "ADJF") or evs[i].pos == "NPRO") and not evs[i].is_oov()

    for i, ev in enumerate(evs):
        # OP1 = lexical predicates; copulas are handled by OP2 exclusively.
        if ev.pos != "VERB" or _is_copula(ev):
            continue
        # OP1: predicate + ALL nominal mentions; word order never drops a participant.
        participants = [ev.span]
        args: list[str] = []
        for j, other in enumerate(evs):
            if j == i or not nominal(j):
                continue
            participants.append(other.span)
            args.append(other.span)
        construction = "NOM+V+ACC"  # declared pattern label; ranking only
        frame = FrameCandidate(
            frame_id=f"F{i}", kind="FLAT", anchor_span=ev.span,
            participants=tuple(participants), arguments=tuple(args),
            construction=construction, rank=len(frames),
            provenance=ResourceProvenance(pattern_ids=("OP1"), resource_versions={"grammar": _GRAMMAR_VERSION}),
        )
        frames.append(frame)
        # Valency check [Rev16/H3]: a verbal frame with zero arguments yields a
        # MissingArgumentCandidate (structural gap confirmed by the schema's cardinality).
        if not args:
            # Three-state machine (V5 §17.3 [H3]): the valency check only POSSIBLY
            # opens a gap; a declared structural link confirms it; nothing is binary.
            confirmed = any(
                ec.antecedent_ref == ev.span or ec.gap_ref in frame.participants
                for ec in state.ellipsis_candidates
            )
            status = "CONFIRMED_GAP" if confirmed else "POSSIBLE_GAP"
            state.missing_argument_candidates.append(MissingArgumentCandidate(
                candidate_id=f"MA-{frame.frame_id}", frame_ref=frame.frame_id, role="ARGUMENT",
                status=status,
                provenance=ResourceProvenance(pattern_ids=("valency_check_v1",), resource_versions={"predicate_schema": "v1"}),
            ))
            state.miss_reports.append(f"{frame.frame_id}: argument gap (valency check, {status})")

    # OP2: copula constructions (explicit copula or ellipsis under 'у'+GEN).
    for i, ev in enumerate(evs):
        if _is_copula(ev):
            poss = [e.span for j, e in enumerate(evs) if nominal(j) and _is_possessor(e, evs[j - 1] if j else None)]
            obj = [e.span for j, e in enumerate(evs) if nominal(j) and not _is_possessor(e, evs[j - 1] if j else None)]
            frames.append(FrameCandidate(
                frame_id=f"C{i}", kind="FLAT", anchor_span=ev.span,
                participants=tuple([*poss, *obj]), arguments=tuple(obj),
                construction="u+GEN+NOM" if poss else "V+ARG", rank=len(frames),
                provenance=ResourceProvenance(pattern_ids=("OP2_copula",), resource_versions={"grammar": _GRAMMAR_VERSION}),
            ))
        elif ev.pos in ("NOUN", "ADJF", "NPRO"):
            prev = evs[i - 1] if i else None
            if _is_possessor(ev, prev) and not any(_is_copula(e) for e in evs):
                # OP2 ellipsis: only when NO copula is present AND the genitive is
                # governed by 'у'. Otherwise the reading stays a decision, not a guess.
                obj = [e.span for j, e in enumerate(evs) if nominal(j) and j != i and not _is_possessor(e, evs[j - 1] if j else None)]
                frames.append(FrameCandidate(
                    frame_id=f"E{i}", kind="FLAT", anchor_span=ev.span,
                    participants=tuple([ev.span, *obj]), arguments=tuple(obj),
                    construction="u+GEN+NOM", copula_ellipsis=True, rank=len(frames),
                    provenance=ResourceProvenance(pattern_ids=("OP2_copula_ellipsis",), resource_versions={"grammar": _GRAMMAR_VERSION}),
                ))

    # OP4_NESTED (Rev18, declared rule [connectives_v1]): a subordinator connective links
    # the following clause to a preceding verbal center. Primary attachment = NEAREST
    # preceding finite verb; alternative attachments are derived by composition.build_graphs
    # (bounded enumeration). No matrix center or no subclause center -> honest
    # STRUCTURE_NOT_COVERED, never a silent skip.
    from ah.formalizer.composition import CONNECTIVES_V1, _CONNECTIVES_VERSION
    for i, ev in enumerate(evs):
        if ev.pos != "CONJ" or (ev.lemma or "").lower() not in CONNECTIVES_V1:
            continue
        next_conn = [j for j in range(i + 1, n)
                     if evs[j].pos == "CONJ" and (evs[j].lemma or "").lower() in CONNECTIVES_V1]
        end = (next_conn[0] - 1) if next_conn else (n - 1)

        def _finite(j: int) -> bool:
            return evs[j].pos == "VERB" and any(
                v.tense in ("past", "present", "future") for v in evs[j].variants)

        sub_nominals = [e.span for j, e in enumerate(evs[i + 1:end + 1]) if nominal(j)]
        centers_before = [j for j in range(i) if _finite(j) and not _is_copula(evs[j])]
        sub_center = next((j for j in range(i + 1, end + 1) if _finite(j)), None)
        if not centers_before or sub_center is None:
            state.diag("STRUCTURE_NOT_COVERED",
                       f"connective '{ev.span}': OP4_NESTED needs a matrix center and a subclause center")
            continue
        frames.append(FrameCandidate(
            frame_id=f"N{i}", kind="NESTED", anchor_span=ev.span,
            participants=tuple(sub_nominals), arguments=tuple(sub_nominals),
            construction=f"SUBORDINATE:{CONNECTIVES_V1[(ev.lemma or '').lower()]}",
            attachment=evs[max(centers_before)].span, rank=len(frames),
            provenance=ResourceProvenance(
                pattern_ids=("OP4_nested",),
                resource_versions={"grammar": _GRAMMAR_VERSION, "connectives": _CONNECTIVES_VERSION}),
        ))

    # OP5 (declared stub): coordination marker between two nominal mentions.
    for i, ev in enumerate(evs):
        if ev.pos == "CONJ" and (ev.lemma or "").lower() in _CONJUNCTIONS:
            left = [e.span for j, e in enumerate(evs[:i]) if nominal(j)]
            right = [e.span for j, e in enumerate(evs[i + 1:]) if nominal(j)]
            if left and right:
                frames.append(FrameCandidate(
                    frame_id=f"K{i}", kind="COORD", anchor_span=ev.span,
                    participants=tuple([*left, *right]), arguments=(),
                    construction="COORD", rank=len(frames),
                    provenance=ResourceProvenance(pattern_ids=("OP5_coordination",), resource_versions={"grammar": _GRAMMAR_VERSION}),
                ))

    state.frames = sorted(frames, key=lambda f: (f.rank != 0, f.rank))
    return state


# --------------------------------------------------------------------------- T3

# Declared slot arities (structural declaration, not per-word knowledge): the
# predicate-value slot relates two entities; a verbal marker is not an argument.
SLOT_ARITY = {"predicate_value": 2}


def _slot_key(frame_id: str, slot_id: str) -> str:
    return f"{frame_id}|{slot_id}"


class OscillationDetector:
    """rev8: oscillation protection on STATE REPETITION with a content-based signature.

    - A repeat of the SAME value with unchanged real grounds is idempotent
      re-confirmation — accepted, NOT frozen (a single flip V1->V2 is not a cycle).
    - Returning to a PRIOR state (same value + same real-ground CONTENT) after having
      left it freezes the slot: no new information, only cycling.
    - The signature compares ground CONTENT ((type, text, value)), not type letters;
      M answers are traces and count as none — repeating an identical M never re-arms.
    - New R/C/D/A content after a freeze re-arms legitimately (revision with new grounds)."""

    def __init__(self) -> None:
        self._history: dict[str, list[tuple[str, tuple]]] = {}
        self.frozen: set[str] = set()
        self._frozen_sig: dict[str, tuple] = {}

    def record(self, slot_id: str, value: str, grounds) -> str:
        sig = real_ground_signature(grounds)
        if slot_id in self.frozen:
            if sig != self._frozen_sig.get(slot_id):
                # New real-ground CONTENT: legitimate re-selection under new information.
                self.frozen.discard(slot_id)
                self._history.setdefault(slot_id, []).append((value, sig))
                return "rearmed"
            return "frozen"
        hist = self._history.setdefault(slot_id, [])
        state_pair = (value, sig)
        if hist and hist[-1] == state_pair:
            return "accepted"  # idempotent re-confirmation: no flip happened
        if any(h == state_pair for h in hist[:-1]):
            self.frozen.add(slot_id)
            self._frozen_sig[slot_id] = sig
            return "frozen"  # back to a prior state without new real grounds
        hist.append(state_pair)
        return "accepted"


def bounded_search(
    domains: dict[str, tuple],
    constraints: list[tuple[tuple[str, ...], frozenset]],
    budget: Budget,
    position: dict | None = None,
):
    """Deterministic enumeration of full assignments with a step budget (rev8).

    RESUMABLE: the traversal position (frame stack + current assignment) is returned
    and may be passed back to a later call — a continuation does NOT re-pay steps
    already executed. ``complete`` is True only when the space was exhausted; an
    incomplete search proves nothing about absence."""
    order = sorted(domains)
    found: list[dict] = []
    if position:
        stack = [tuple(x) for x in position.get("stack", [])]
        assign = dict(position.get("assign", {}))
    else:
        stack = [(0, 0)] if order else []
        assign = {}

    def satisfies(a: dict) -> bool:
        for slot_ids, forbidden in constraints:
            if all(s in a for s in slot_ids):
                if tuple(a[s] for s in slot_ids) in forbidden:
                    return False
        return True

    while stack and budget.search_steps < budget.search_step_limit:
        slot_pos, value_idx = stack[-1]
        values = domains[order[slot_pos]]
        if value_idx >= len(values):
            assign.pop(order[slot_pos], None)
            stack.pop()
            continue
        budget.search_steps += 1
        slot = order[slot_pos]
        assign[slot] = values[value_idx]
        stack[-1] = (slot_pos, value_idx + 1)
        if slot_pos == len(order) - 1:
            if satisfies(assign):
                found.append(dict(assign))
            del assign[slot]
        else:
            stack.append((slot_pos + 1, 0))

    complete = not stack
    new_position = {"stack": [tuple(x) for x in stack], "assign": dict(assign)}
    return found, complete, new_position


def t3(
    state: FormalizationState,
    schema,
    selector,
    detector: OscillationDetector | None = None,
) -> FormalizationState:
    """Bounded selection. Every pick is PROVISIONAL; a semantic outcome is granted by T4 only."""
    det = detector or OscillationDetector()
    for frame in state.frames:
        if frame.kind not in ("FLAT", "NESTED"):
            # OP5 COORD remains a declared stub: honest incompleteness, never silent.
            state.diag(
                "STRUCTURE_NOT_COVERED",
                f"{frame.kind} frame {frame.frame_id}: declared in the grammar (OP5), exercised in Phase 2",
            )
            continue
        candidates = candidates_for_slot(schema, SLOT_ARITY["predicate_value"])
        dec = Decision(slot_id="predicate_value", frame_id=frame.frame_id, candidates=candidates)
        for fact in state.context_facts:
            # Declared contextual statements are C grounds (declared INPUTS). They are
            # slot-level: which value a statement supports is the model's judgment (M),
            # recorded with its I/O — never a self-legalizing assumption.
            dec.grounds.append(Ground("C", f"contextual statement: {fact}"))
        key = _slot_key(frame.frame_id, "predicate_value")
        state.decisions[key] = dec

        if state.budget.llm_exhausted:
            state.diag("BUDGET_EXHAUSTED", f"no LLM budget left for {key}")
            break

        mentions = {f"M{k}": span for k, span in enumerate(frame.participants)}
        prompt = build_selection_prompt(
            slot_id="predicate_value",
            frame_id=frame.frame_id,
            context_span=state.text,
            mentions=mentions,
            schema=schema,
            contextual_statements=state.context_facts,
            candidates=candidates,  # rev8: THIS decision's closed set, not the whole schema
        )
        try:
            raw = selector.select(prompt)
        except Exception as exc:  # ProviderUnavailableError and friends
            state.budget.spend_llm(failed=True)  # exactly ONE charge per attempt (rev8)
            state.diag("PROVIDER_UNAVAILABLE", f"{key}: {exc}")
            break

        try:
            resp = validate_selection_response(raw, schema, allowed=frozenset(candidates))
        except ProtocolError as exc:
            state.budget.spend_llm(failed=True)  # rejected call: one charge, flagged failed
            state.diag("PROTOCOL_ERROR", f"{key}: {exc}")
            continue

        state.budget.spend_llm()  # successful call: exactly ONE charge (rev8)
        dec.selector_outcome = resp.outcome
        dec.last_prompt = prompt      # rev8: recorded I/O — the run is replayable
        dec.raw_response = raw
        if resp.selected:
            verdict = det.record(key, "/".join(resp.selected), dec.grounds)
            if verdict == "frozen":
                state.diag("OSCILLATION_FROZEN", f"{key}: state repetition without new real grounds")
                continue
            dec.selected = tuple(resp.selected)
            dec.lifecycle = "PROVISIONAL"  # uniqueness at T3 proves nothing yet
            bound = resp.selected[0] if len(resp.selected) == 1 else None
            dec.grounds.append(Ground(
                "M",
                f"selector chose {list(resp.selected)}; note: {resp.note}",
                value=bound,  # ONE_SELECTED binds the trace to its value; MULTIPLE stays slot-level
            ))
    return state


# --------------------------------------------------------------------------- T4

_POSITIVE = {"R", "C", "D", "A", "M", "W"}  # W: world-knowledge / memory channel (V5 §15.5/§17.4)


def _cluster_valid(state: FormalizationState, key: str, dec: Decision, schema) -> bool:
    """rev8: the REAL joint check. (1) every selected value lies in THIS decision's
    closed candidate set; (2) it matches the slot's declared arity; (3) no declared
    ConstraintEdge between decisions of this cluster is violated."""
    for v in dec.selected:
        rel = schema.relations.get(v)
        if rel is None or v not in dec.candidates:
            return False  # selection outside the decision's declared set
        if rel.arity != SLOT_ARITY[dec.slot_id]:
            return False
    for edge in state.constraints:
        other_key = edge.slot_b if edge.slot_a == key else (edge.slot_a if edge.slot_b == key else None)
        if other_key is None:
            continue
        other = state.decisions.get(other_key)
        if other is None or not other.selected:
            continue
        for va in dec.selected:
            for vb in other.selected:
                pair = (va, vb) if edge.slot_a == key else (vb, va)
                if pair in edge.forbidden:
                    return False
    return True


# --------------------------------------------------------------------------- TD (V5 §15.4)

# Declared versioned policy [C] (V5 §15.4): lexicographic ranking criteria, no criterion
# is hardcoded in the core — a new criterion = a NEW POLICY VERSION.
COREF_POLICY = {
    "policy_id": "coref_policy_v1",
    "version": "v1",
    "ranking_criteria": ("subject", "recency"),
}


def _anaphora_features(ev: TokenEvidence) -> tuple:
    """(gender, number) of the anaphora's top variant — R1 features only."""
    if not ev.variants:
        return (None, None)
    top = max(ev.variants, key=lambda v: v.score)
    return (top.gender, top.number)


def _agrees(anaphora: tuple, mention_ev: TokenEvidence | None) -> bool:
    """Declared HARD FILTER (structural rule under the two-tier invariant): gender/number
    agreement from R1 features. A candidate agrees when ANY of its variants matches the
    anaphora's top variant on every feature KNOWN on both sides; unknown features impose
    no constraint and never reject. Memory-channel mentions have no R1 features here —
    they are not filterable by morphology (their channel is memory, §17.4)."""
    if mention_ev is None:
        return True
    ag, an = anaphora
    for v in mention_ev.variants:
        g_ok = ag is None or v.gender is None or v.gender == ag
        n_ok = an is None or v.number is None or v.number == an
        if g_ok and n_ok:
            return True
    return False


def _subject_positions(evs) -> set:
    """Declared syntax signal for the 'subject' policy criterion: a nominal position is a
    subject when it is the NEAREST nominal preceding some finite-verb center."""
    centers = [j for j, e in enumerate(evs)
               if e.pos == "VERB" and any(v.tense in ("past", "present", "future") for v in e.variants)]
    subjects: set[int] = set()
    for c in centers:
        for j in range(c - 1, -1, -1):
            if evs[j].pos in ("NOUN", "ADJF") and not evs[j].is_oov():
                subjects.add(j)
                break
    return subjects


def td(state: FormalizationState) -> FormalizationState:
    """ReferenceResolver [Rev16/H2]: TD — NOT SRL — creates ReferenceCandidates.

    Declared policy coref_policy_v1: anaphoric mentions are 3rd-person NPRO; the
    antecedent set = nominal mentions of the observation + the declared memory window
    (journal, §17.4/H5). Candidates are built through FOUR DECLARED evidence channels:
      morphology — hard agreement filter on R1 features; a failing observed candidate is
                   RECORDED as rejected with a D-trace (I29), never deleted silently;
      syntax     — subject/recency ranking by the declared policy criteria (ranks, not cuts);
      discourse  — the mention lies inside the observation window (declared NQ7 default);
      memory     — journal-window mentions enter as W-channel evidence only.
    The pair 'mention = antecedent' exists ONLY inside a reference decision; no identity
    link is created here or before consolidation (I24)."""
    state.require_structures_open("TD")
    evs = state.evidence
    prov = ResourceProvenance(
        pattern_ids=(COREF_POLICY["policy_id"],),
        resource_versions={"coreference_policy": COREF_POLICY["version"]},
    )
    subjects = _subject_positions(evs)
    for i, ev in enumerate(evs):
        if ev.pos != "NPRO" or not any(v.person == "3rd" for v in ev.variants):
            continue
        anaphora = _anaphora_features(ev)
        observed = [(j, e) for j, e in enumerate(evs)
                   if j != i and e.pos in ("NOUN", "ADJF") and not e.is_oov()]
        survivors: list[tuple[str, TokenEvidence | None, int, bool, list]] = []
        for j, m in observed:
            if not _agrees(anaphora, m):
                feats = sorted(
                    f"{v.gender or '?'}-{v.number or '?'}" for v in m.variants
                )
                state.reject(
                    candidate_id=f"antecedent:{m.span}", stage="TD",
                    reason=(f"failed the declared agreement filter ({COREF_POLICY['policy_id']}): "
                           f"anaphora '{ev.span}' is {anaphora[0]}/{anaphora[1]}, candidate features {feats}"),
                    provenance=prov,
                )
                continue
            evd = [
                ("morphology", f"agrees with anaphora '{ev.span}' on {anaphora} (declared hard filter)"),
                ("syntax", f"{'subject' if j in subjects else 'non-subject'} position; "
                          f"ranked by policy criteria {COREF_POLICY['ranking_criteria']}"),
                ("discourse", "nominal mention inside the observation window (declared NQ7 default)"),
            ]
            survivors.append((m.span, m, j, j in subjects, evd))
        # Declared ranking [Rev13]: lexicographic by policy criteria — subject first,
        # then recency (later position first); memory mentions follow in declared order.
        survivors.sort(key=lambda s: (0 if s[3] else 1, -s[2]))
        for m in state.memory_mentions:
            if not any(span == m for span, _, _, _, _ in survivors):
                survivors.append((m, None, len(evs), False, [
                    ("memory", f"mention '{m}' from the declared journal window (V5 §17.4/H5)"),
                ]))
        cands = [span for span, _, _, _, _ in survivors]
        evid = [(cat, det) for _, _, _, _, evd in survivors for cat, det in evd]
        state.reference_candidates.append(ReferenceCandidate(
            mention_id=ev.span, candidates=tuple(cands), evidence=evid, provenance=prov,
        ))
        dec = Decision(slot_id="reference", frame_id=ev.span, candidates=tuple(cands), provenance=prov)
        for span, mev, _, _, _ in survivors:  # value-specific positive grounds per candidate
            if mev is not None:
                dec.grounds.append(Ground("R", f"antecedent '{span}' from observation (channels: morphology/syntax/discourse)", value=span))
            else:
                dec.grounds.append(Ground("W", f"antecedent '{span}' from the memory channel (declared journal window, §17.4/H5)", value=span))
        if cands:  # single survivor or several: T4 grants the outcome; all stay admissible
            dec.selected = tuple(cands)
            dec.lifecycle = "PROVISIONAL"
        state.decisions[f"reference|{ev.span}"] = dec
    return state


# --------------------------------------------------------------------------- traceability (§18.2/I23)


def rejected_alternatives(state: FormalizationState):
    """I29/§2.3 audit trail: every candidate that left the active set, with the stage,
    the declared rule that rejected it (D-trace) and provenance. Silent deletion = none."""
    return list(state.rejections)


def trace_decision(state: FormalizationState, key: str):
    """Reconstruct the provenance chain for one decision (V5 §18.2/I23, Phase 1 scope).

    Ordered raw -> structural -> decision:
      RawInput tokens -> TokenHypothesis/BoundaryCandidate/ClauseCandidate/EllipsisCandidate
      touching them -> FrameCandidate -> Decision.
    SemanticGraphCandidate and Canonical Memory are Phase 2 objects: I25 forbids any write
    before the commit stage, so in Phase 1 the chain legitimately ENDS at the Decision —
    nothing beyond it exists yet (honest incompleteness, not a missing link)."""
    dec = state.decisions[key]
    spans: set[str] = set()
    frame = next((f for f in state.frames if f.frame_id == dec.frame_id), None)
    if frame is not None:
        spans.update(frame.participants)
    elif dec.slot_id == "reference":
        spans.add(dec.frame_id)  # the anaphoric span itself
    chain: list[tuple[str, str, ResourceProvenance]] = []
    for ev in state.evidence:  # raw input first
        if ev.span in spans:
            chain.append(("TokenEvidence", ev.span, ResourceProvenance()))
    for h in state.token_hypotheses:  # then the structural layer over those tokens
        if h.span_ref in spans:
            chain.append(("TokenHypothesis", h.hypothesis_id, h.provenance))
    for bc in state.boundary_candidates:
        if 0 <= bc.position < len(state.evidence) and state.evidence[bc.position].span in spans:
            chain.append(("BoundaryCandidate", bc.candidate_id, bc.provenance))
    for cc in state.clause_candidates:
        touched = any(
            idx < len(state.evidence) and state.evidence[idx].span in spans
            for rng in cc.segmentation for idx in range(rng[0], rng[1] + 1)
        )
        if touched:
            chain.append(("ClauseCandidate", cc.candidate_id, cc.provenance))
    for ec in state.ellipsis_candidates:
        if ec.gap_ref in spans or (ec.antecedent_ref and ec.antecedent_ref in spans):
            chain.append(("EllipsisCandidate", ec.candidate_id, ec.provenance))
    if frame is not None:  # ...through the frame...
        chain.append(("FrameCandidate", frame.frame_id, frame.provenance))
    chain.append(("Decision", key, dec.provenance))  # ...to the decision
    return chain


def t4(state: FormalizationState, schema) -> FormalizationState:
    """Joint validation — the ONLY place a semantic outcome is granted (rev7/rev8).

    RESOLVED requires ALL THREE simultaneously:
      (a) a VALUE-SPECIFIC positive ground for the selected value (Ground.value == v;
          slot-level grounds license the slot but ground no individual candidate);
      (b) search_complete — a validated protocol response over THIS decision's closed
          candidate set (the validator checked against it, so the selector answered
          on exactly that set);
      (c) cluster validity — selected values inside the candidates, arity-compatible,
          and consistent with declared constraint edges.

    AMBIGUOUS requires EVERY survivor to have its own value-specific positive ground
    (§1.4: several non-contradictory formulas alone are not a ground). Otherwise the
    outcome is UNRESOLVED + diagnostic — never AMBIGUOUS/RESOLVED by default."""
    for key, dec in state.decisions.items():
        if dec.slot_id == "boundary":
            # Structural alternatives: without new grounds no segmentation is chosen;
            # the survivors stay linked (I29) and nothing downstream commits on them.
            if not dec.selected:
                dec.outcome = "UNRESOLVED"
            continue
        if dec.slot_id == "reference":
            per_value = {g.value for g in dec.grounds if g.type in _POSITIVE and g.value is not None}
            if not dec.candidates:
                dec.outcome = "UNRESOLVED"
                state.diag("REFERENCE_UNKNOWN", f"{key}: no admissible antecedent in observation or memory window")
                state.miss_reports.append(f"{key}: REFERENCE_UNKNOWN (no antecedent)")
            elif len(dec.selected) == 1:
                v = dec.selected[0]
                if v in per_value:
                    dec.outcome = "RESOLVED"
                else:
                    dec.outcome = "UNRESOLVED"
                    state.diag("NO_GROUNDED_CANDIDATE", f"{key}: no value-specific ground for '{v}'")
            elif [v for v in dec.selected if v not in per_value]:
                dec.outcome = "UNRESOLVED"
                state.diag("NO_GROUNDED_CANDIDATE", f"{key}: survivors lack value-specific grounds")
            else:
                dec.outcome = "AMBIGUOUS"  # every survivor grounded on its own evidence
            continue
        if dec.slot_id != "predicate_value":
            continue
        search_complete = bool(dec.selector_outcome)  # validated response over the closed set
        if not dec.selected:
            if dec.selector_outcome == "NONE_FIT":
                dec.outcome = "NO_CANDIDATE"
                state.miss_reports.append(f"{key}: no declared relation fits (demo boundary)")
            elif dec.selector_outcome == "INSUFFICIENT_CONTEXT":
                dec.outcome = "INSUFFICIENT_CONTEXT"
            continue

        per_value = {g.value for g in dec.grounds if g.type in _POSITIVE and g.value is not None}
        cluster_ok = _cluster_valid(state, key, dec, schema)

        def fail(reason: str, code: str) -> None:
            dec.outcome = "UNRESOLVED"
            state.diag(code, f"{key}: {reason}")

        if len(dec.selected) == 1:
            v = dec.selected[0]
            if not cluster_ok:
                fail("selected value fails the joint cluster check", "CLUSTER_CONFLICT")
            elif v not in per_value:
                fail("no value-specific positive ground for the selected value", "NO_GROUNDED_CANDIDATE")
            else:
                dec.outcome = "RESOLVED"  # (a)+(b)+(c) all hold; still PROVISIONAL (T5 commits)
        else:
            ungrounded = [v for v in dec.selected if v not in per_value]
            if not cluster_ok:
                fail("survivors fail the joint cluster check", "CLUSTER_CONFLICT")
            elif ungrounded:
                fail(f"no value-specific positive ground for {ungrounded}", "NO_GROUNDED_CANDIDATE")
            else:
                dec.outcome = "AMBIGUOUS"  # proven ambiguity, per-value grounds on record
    return state


# --------------------------------------------------------------------------- run


def run(
    text: str,
    schema,
    selector,
    morph: MorphProvider | None = None,
    context_facts: tuple[str, ...] = (),
    budget: Budget | None = None,
    memory_mentions: tuple[str, ...] = (),  # declared journal-window input (V5 §17.4/H5)
) -> FormalizationState:
    """Full Phase 1 vertical: RawInput -> T0 -> SRL -> T1 -> T2 -> TD -> [I30 closure]
    -> T3/T4. Consolidator/Canonical Memory are Phase 2; nothing here commits facts."""
    state = t0(text)
    state.context_facts = context_facts
    state.memory_mentions = tuple(memory_mentions)
    if budget is not None:
        state.budget = budget
    srl(state, morph=morph)
    t1(state, morph=morph)
    t2(state)
    td(state)
    structural_seal(state)  # WP1.1/§4.3: closure validation + structural hash + freeze (I30)
    t3(state, schema, selector)
    t4(state, schema)
    return state


def revise(
    base_state: FormalizationState,
    schema,
    selector,
    morph: MorphProvider | None = None,
    memory_mentions: tuple[str, ...] = (),  # updated journal window (GENERATION channel)
    context_facts: tuple[str, ...] | None = None,  # None -> keep the base version's facts
) -> FormalizationState:
    """Rev18/check4 — context revision of the SAME ObservationRecord.

    The source text does not change; the journal window (GENERATION channel) may. Result:
    same observation_id (source_uid), interpretation_version = base + 1, a fresh
    CandidateIR. No canonical fact is auto-created (I25): Phase 1 has no commit stage —
    every decision stays <= PROVISIONAL."""
    st = run(
        base_state.text, schema, selector, morph=morph,
        context_facts=context_facts if context_facts is not None else base_state.context_facts,
        memory_mentions=memory_mentions,
    )
    st.interpretation_version = base_state.interpretation_version + 1
    return st
