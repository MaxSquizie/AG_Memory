"""Event-relative parents consume typed nominal children, not PREP+NOUN hacks."""
import re
from .canonical_ledger import digest
from .component_probe import _probe
from .component_source import view
from .composition_tree import InputSlot, roots, expression, internalize


def compose(state,release,selector,region,tokens,cfg,child_composer):
    from .component_phrases import prepositional_groups
    raw=view(state,region,tokens)
    options={}
    for rule in release.entries('ScopeLexicon'):
        if 'TEMPORAL_NOMINAL' not in rule.get('attachment_kinds',()):continue
        for match in re.finditer(rule['pattern'],raw,re.I):
            lo,hi=region.source_range[0]+match.start(),region.source_range[0]+match.end()
            for head,group in prepositional_groups(tokens).items():
                prep=next(t for t in tokens if t.token_id==group['token_ref'])
                if (prep.start,prep.end)!=(lo,hi):continue
                anchor=next(t for t in tokens if t.token_id==head)
                cases=frozenset(rule['restriction_pattern']['anchor_cases'])
                if not any(v.pos=='NOUN' and v.cases & cases for v in anchor.variants):continue
                start=tokens.index(prep); first=tokens.index(anchor)
                for end in range(first+1,len(tokens)+1):
                    last=tokens[end-1]
                    if end>first+1 and any(v.pos=='VERB' for v in last.variants):break
                    if not any(v.pos in {'NOUN','NPRO'} for v in last.variants):continue
                    body=tokens[start+1:end]
                    parent=tokens[:start]+tokens[end:]
                    if not parent:continue
                    cid='relative-child:'+digest([region.region_id,rule,head,[t.token_id for t in body]])
                    options[cid]=(rule,body,parent,InputSlot('EVENT_DESCRIPTION',head,cases),prep)
    if not options:return None
    if len(options)>cfg['max_candidates']:
        state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id);return []
    choices=[{'candidate_id':cid,'label':r['operator']+' with nominal event anchor «'+
              state.text[body[0].start:body[-1].end]+'»; remaining content «'+' '.join(t.span for t in parent)+'»'}
             for cid,(r,body,parent,slot,prep) in options.items()]
    key=region.region_id+'|relative-child:'+digest(choices)
    selected=_probe(state,selector,release,key,'temporal_boundary',choices,
                    state.text[slice(*region.source_range)],region.source_range,
                    question='Choose the complete nominal description governed by the temporal relation. '
                    'Include its adjectives and nominal dependents; do not absorb the subject of the following clause. '
                    'This chooses a child boundary, not an absolute date or the truth of the anchor event.', target_refs=tuple(t.token_id for t in tokens))
    if selected not in options:
        state.diag('COMPONENT_TEMPORAL_SCOPE_UNRESOLVED',region.region_id);return []
    rule,body,parent,slot,prep=options[selected]
    children=child_composer(body,slot)
    parents=child_composer(parent,None)
    from .composition_children import select_child
    cr=select_child(state,release,selector,region,children,'EVENT_DESCRIPTION',
        'This child is the event anchor of '+rule['operator']+', governed by «'+prep.span+'».')
    pr=select_child(state,release,selector,region,parents,'PROPOSITION',
        'This child is the main clause with a '+rule['operator']+' event anchor.')
    frames=[*parents,*children]
    if cr is None or pr is None:
        for f in frames:f.semantic['structural_unresolved']=True
        state.diag('COMPOSITION_SLOT_UNCLOSED',region.region_id);return frames
    tree={'operator':rule['operator'],'operands':[expression(pr),expression(cr)],
          'anchor_refs':[prep.token_id],
          'source_projection':{'rule_id':'TEMPORAL_MAIN_CLAUSE','operand':0,'decision_ref':key}}
    internalize(frames,cr,pr)
    pr.semantic['component_scope_tree']=tree
    pr.semantic['operator_forest']=[tree]
    pr.semantic['relative_composition_decision']=key
    state.syntax_trace.append({'kind':'RELATIVE_COMPOSITION','decision_ref':key,'tree':tree,
                               'parent_tokens':[t.token_id for t in parent],
                               'anchor_tokens':[t.token_id for t in body]})
    return frames
