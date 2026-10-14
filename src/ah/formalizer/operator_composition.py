"""Unary operator slots reuse the ordinary child composer at every depth."""
import re
from .operator_algebra import OPERATORS
from .component_source import view
from .composition_tree import expression, roots, internalize
from .scope_assignment import assign
from .canonical_ledger import digest
from dataclasses import replace
from .composition_tree import InputSlot


def lexical_matches(state, release, region, tokens):
    raw = view(state, region, tokens)
    matches = {}
    for rule in release.entries('ScopeLexicon'):
        operator = OPERATORS.get(rule.get('operator'))
        if operator is None or (operator.arity_min, operator.arity_max) != (1, 1):
            continue
        for match in re.finditer(rule['pattern'], raw, re.I):
            lo, hi = region.source_range[0]+match.start(), region.source_range[0]+match.end()
            anchors = [t for t in tokens if lo <= t.start and t.end <= hi]
            if not anchors or any(v.pos=='INFN' for t in anchors for v in t.variants):
                continue
            key = (lo, hi, operator.name)
            matches[key] = anchors
    return matches


def compose(state, release, selector, region, tokens, cfg, child_composer, request=None, outer=None):
    matches = lexical_matches(state, release, region, tokens)
    if not matches:
        return None
    spans = sorted(set((lo,hi) for lo,hi,op in matches))
    if any(a[1] > b[0] for a,b in zip(spans,spans[1:])) or len(spans) != len(matches):
        state.diag('OPERATOR_LEXICAL_SCOPE_UNRESOLVED',region.region_id)
        return []
    consumed = {t.token_id for anchors in matches.values() for t in anchors}
    governors={t.token_id:t for anchors in matches.values() for t in anchors
               if any(v.pos=='VERB' and v.mood!='imperative' for v in t.variants)}
    owned = [t for t in tokens if t.token_id not in consumed]
    if not owned:
        state.diag('COMPOSITION_SLOT_UNCLOSED',region.region_id)
        return []
    if len(governors)>1 or governors and not any(v.pos=='INFN' for t in owned for v in t.variants):
        state.diag('OPERATOR_CONTROL_UNRESOLVED',region.region_id);return []
    child_request=replace(request or InputSlot(),agreement_source=next(iter(governors.values()))) if governors else request
    frames = child_composer(owned,child_request)
    from .composition_children import select_child
    root=select_child(state,release,selector,region,frames,'PROPOSITION under '+str([k[2] for k in matches]),
                      'Unary operators take this whole child or a licensed descendant scope.')
    if root is None:
        state.diag('OPERATOR_CHILD_UNRESOLVED',region.region_id)
        for f in frames:f.semantic['structural_unresolved']=True
        return frames
    operators, modifiers = {}, []
    ordered=sorted(matches.items(), reverse=True)
    if outer is not None:
        if outer not in matches:
            state.diag('OPERATOR_LEXICAL_SCOPE_UNRESOLVED',region.region_id)
            return []
        ordered=[item for item in ordered if item[0]!=outer]+[(outer,matches[outer])]
    for (lo,hi,op), anchors in ordered:
        fid = 'operator-slot:' + digest([region.region_id,lo,hi,op])
        operators[fid] = (op,[t.token_id for t in anchors])
        modifiers.append({'id':fid,'label':op+' «'+state.text[lo:hi]+'»',
                          **({'allowed_paths':[()]} if (lo,hi,op)==outer else {})})
    result = assign(state,release,selector,region,expression(root),modifiers,cfg,
                    node_labels={f.frame_id:'«'+f.anchor_span+' '+', '.join(f.arguments)+'»' for f in frames})
    if result is None:
        for f in frames:f.semantic['structural_unresolved']=True
        return frames
    tree, contents, decisions = result
    def lower(node):
        if node.get('frame_ref') in operators:
            fid = node['frame_ref'];op,anchors = operators[fid]
            return {'operator':op,'operands':[lower(contents[fid])],'anchor_refs':anchors}
        if 'operands' in node:
            return {**node,'operands':[lower(c) for c in node['operands']]}
        return node
    tree = lower(tree)
    internalize(frames)
    root.semantic['component_scope_tree']=tree
    root.semantic['operator_forest']=[tree]
    root.semantic['operator_scope_decision_refs']=decisions
    state.syntax_trace.append({'kind':'OPERATOR_COMPOSITION','tree':tree,'decision_refs':decisions,
                               'consumed_token_refs':sorted(consumed),'region_ref':region.region_id})
    return frames
