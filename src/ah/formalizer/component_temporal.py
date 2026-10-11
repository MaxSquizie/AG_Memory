"""Released event-relative adjuncts; no invented date or asserted anchor event."""
import re
from .component_phrases import prepositional_groups


def relative_adjuncts(state,release,region,tokens):
    raw=state.text[slice(*region.source_range)]; groups=prepositional_groups(tokens)
    evidence={e.token_id:e for e in tokens}; out=[]
    for rule in release.entries('ScopeLexicon'):
        if 'TEMPORAL_NOMINAL' not in rule.get('attachment_kinds',()): continue
        for match in re.finditer(rule['pattern'],raw,re.I):
            lo,hi=region.source_range[0]+match.start(),region.source_range[0]+match.end()
            for head,g in groups.items():
                prep=evidence[g['token_ref']]
                if (prep.start,prep.end)!=(lo,hi): continue
                anchor=evidence[head]
                cases=set(rule['restriction_pattern']['anchor_cases'])
                noun_variants=[v for v in anchor.variants if v.pos=='NOUN' and set(v.cases)&cases]
                if not noun_variants: continue
                # A known noun requires its own licensed event schema. Never
                # bypass a broken known mapping by inventing an open anchor.
                known=any(s['lemma']==v.lemma and s['POS']==v.pos for s in release.entries('R-S') for v in noun_variants)
                if known or not release.entries('OpenTemplatePolicy')[0]['allow']: continue
                # Modified/ambiguous nominal content needs another composition;
                # an adjective may not be dropped from the event anchor.
                if len(g['anchor_refs'])!=2 or len({v.lemma for v in noun_variants})!=1: continue
                out.append({'operator':rule['operator'],'anchor_ref':head,
                    'anchor_surface':anchor.span,'anchor_lemma':noun_variants[0].lemma,
                    'anchor_refs':g['anchor_refs'],'source_range':g['source_range'],
                    'preposition_ref':g['token_ref'],'resource_pattern':rule['pattern']})
    # Two released interpretations of the same source group need alternatives,
    # not an arbitrary last matching rule.
    unique={repr(sorted(row.items())):row for row in out}
    out=list(unique.values())
    return [] if len({r['anchor_ref'] for r in out})!=len(out) else out


def questions(rows):
    return [{'kind':'WHEN_RELATION','operator':r['operator'],
        'anchor_refs':r['anchor_refs'],'source_range':r['source_range'],
        'children':[{'kind':'EVENT_ANCHOR','anchor_ref':r['anchor_ref'],
                     'asserted':False,'calendar_time':None}]} for r in rows]
