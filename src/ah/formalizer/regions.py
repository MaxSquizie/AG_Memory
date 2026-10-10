"""Addressable reading regions. Boundaries propose locality, never truth scope.

The containment tree and overlapping semantic candidates are separate: punctuation
cannot discard a cross-boundary attachment. Token IDs always name original spans.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from bisect import bisect_left
import re

from .canonical_ledger import digest


@dataclass(frozen=True)
class TextRegion:
    region_id: str
    kind: str
    source_range: tuple[int, int]
    token_refs: tuple[str, ...]
    parent_ref: str | None
    boundary_status: str = "PROVISIONAL"
    grounds: tuple[str, ...] = ()


@dataclass
class RegionForest:
    source_id: str
    regions: list[TextRegion] = field(default_factory=list)
    candidates: list[dict] = field(default_factory=list)
    dependencies: list[dict] = field(default_factory=list)

    def container(self, start, end, *, kinds=None):
        eligible = [r for r in self.regions if r.kind != 'TOKEN'
                    and (kinds is None or r.kind in kinds)
                    and r.source_range[0] <= start and end <= r.source_range[1]]
        return min(eligible, key=lambda r: (r.source_range[1]-r.source_range[0], r.region_id))

    def to_dict(self):
        return asdict(self)

    def attach_frames(self, frames):
        """Keep every alternative; shared anchors expose transverse dependencies."""
        self.candidates = []
        self.dependencies = []
        owners = {}
        for f in sorted(frames, key=lambda f: f.frame_id):
            region = self.container(*f.source_range)
            anchors = tuple(dict.fromkeys((f.predicate_token_ref, *f.argument_token_refs)))
            self.candidates.append({'candidate_id': f.frame_id, 'region_ref': region.region_id,
                                    'source_range': f.source_range, 'anchor_refs': anchors,
                                    'hypothesis_ref': f.semantic.get('hypothesis')})
            for anchor in anchors:
                owners.setdefault(anchor, []).append(f.frame_id)
        for anchor, refs in sorted(owners.items()):
            if len(refs) > 1:
                self.dependencies.append({'kind': 'SHARED_ANCHOR', 'anchor_ref': anchor,
                                          'candidate_refs': sorted(refs)})


def build_regions(text, evidence, source_id):
    forest = RegionForest(source_id)
    evidence = sorted(evidence, key=lambda e: e.start)
    offsets = [e.start for e in evidence]

    def within(start, end):
        return evidence[bisect_left(offsets, start):bisect_left(offsets, end)]

    def add(kind, start, end, parent, grounds=()):
        rid = 'region:' + digest([source_id, kind, start, end])
        tokens = tuple(e.token_id for e in within(start, end) if e.end <= end)
        r = TextRegion(rid, kind, (start, end), tokens, parent,
                       'SOURCE' if kind in {'DOCUMENT', 'TOKEN'} else 'PROVISIONAL', grounds)
        forest.regions.append(r)
        return r

    root = add('DOCUMENT', 0, len(text), None)
    starts = [0, *(m.end() for m in re.finditer(r'\n[ \t]*\n+', text))]
    ends = [*starts[1:], len(text)]
    for start, end in zip(starts, ends):
        if not text[start:end].strip():
            continue
        paragraph = add('PARAGRAPH', start, end, root.region_id, ('LAYOUT',))
        cursor = start
        # These are tentative read windows, including punctuation inside quotes.
        # Scope closure is proved by the candidate graph, never this split.
        stops = [e.end for e in within(start, end) if e.span in {'.', '!', '?'}]
        for stop in dict.fromkeys([*stops, end]):
            if stop <= cursor:
                continue
            sentence = add('SENTENCE', cursor, stop, paragraph.region_id, ('PUNCTUATION',))
            clause_start = cursor
            clause_stops = [e.end for e in within(cursor, stop) if e.span in {',', ';', ':'}]
            for clause_end in dict.fromkeys([*clause_stops, stop]):
                if clause_end <= clause_start:
                    continue
                clause = add('CLAUSE_WINDOW', clause_start, clause_end, sentence.region_id, ('PUNCTUATION',))
                for e in within(clause_start, clause_end):
                    if clause_start <= e.start and e.end <= clause_end:
                        add('TOKEN', e.start, e.end, clause.region_id)
                clause_start = clause_end
            cursor = stop
    return forest


def reference_goal(state, mention_ref):
    """A question about an existing unresolved slot, not a guessed identity."""
    evidence = {e.token_id: e for e in state.evidence}
    mention = evidence[mention_ref]
    owners = [f for f in state.frames if mention_ref in f.argument_token_refs]
    start = min([mention.start, *(f.source_range[0] for f in owners)])
    end = max([mention.end, *(f.source_range[1] for f in owners)])
    region = state.region_forest.container(start, end, kinds={'DOCUMENT', 'PARAGRAPH', 'SENTENCE'})
    return {'kind': 'REFERENCE', 'decision_ref': mention_ref+'|reference',
            'region_ref': region.region_id, 'source_range': region.source_range,
            'mention_ref': mention_ref, 'cue_token_refs': region.token_refs}
