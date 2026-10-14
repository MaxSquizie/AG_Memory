"""Local scope assignment with shared children, before lexical materialization.

The same operation inserts a modifier at a slot of a single event or a
coordinated tree. Alternatives differ in one edge; no permutations of bundles.
"""
from copy import deepcopy
from collections import deque
from .canonical_ledger import digest
from .composition_tree import reference
from .component_probe import _probe


def expanded_leaves(tree,contents,seen=frozenset()):
    fid=tree.get('frame_ref')
    if fid is not None:
        if fid in seen:raise ValueError('COMPOSITION_CYCLE')
        return {fid}|(expanded_leaves(contents[fid],contents,seen|{fid}) if fid in contents else set())
    return set().union(*(expanded_leaves(c,contents,seen) for c in tree.get('operands',())))


def positions(tree, contents, path=(), active=frozenset()):
    # Bound variables, time literals and counts are typed values, not slots
    # where a proposition modifier/operator may be inserted.
    if 'frame_ref' not in tree and 'operator' not in tree:return
    yield path, tree
    if 'frame_ref' in tree and tree['frame_ref'] in contents:
        fid = tree['frame_ref']
        if fid in active:
            raise ValueError('COMPOSITION_CYCLE')
        yield from positions(contents[fid], contents, (*path, ('content', fid)), active | {fid})
    else:
        children=tree.get('operands',())
        # A flat n-ary coordinate node may acquire an immediate subgroup.
        # Propose one interval edge, never full combinations of groupings.
        if tree.get('operator')=='AND' and len(children)>2:
            for start in range(len(children)):
                for end in range(start+2,len(children)+1):
                    if start==0 and end==len(children):continue
                    yield (*path,('group',(start,end))),{'operator':'AND','operands':list(children[start:end])}
        for index, child in enumerate(tree.get('operands', ())):
            yield from positions(child, contents, (*path, ('operand', index)), active)


def replace(tree, contents, path, replacement):
    """Persistent expression update; lexical child identity is preserved."""
    if not path:
        return deepcopy(replacement)
    (kind, key), *tail = path
    if kind == 'content':
        contents[key] = replace(contents[key], contents, tail, replacement)
        return tree
    result = dict(tree)
    result['operands'] = list(tree['operands'])
    if kind=='group':
        if tail:raise ValueError('COMPOSITION_GROUP_PATH_INVALID')
        start,end=key
        result['operands'][start:end]=[deepcopy(replacement)]
        return result
    result['operands'][key] = replace(result['operands'][key], contents, tail, replacement)
    return result


def assign(state, release, selector, region, tree, modifiers, cfg, *, contents=None, node_labels=None):
    """Return a selected topology plus explicit per-modifier content slots.

    Each input has id/label and optional allowed_paths/shared_content. The
    caller supplies type/ownership constraints; unknown compatibility is never
    silently accepted. Decision IDs include the already established subtree.
    """
    contents = deepcopy(contents or {})
    tree = deepcopy(tree)
    labels = {**(node_labels or {}), **{m['id']: m['label'] for m in modifiers}}
    decisions = []
    def describe(node):
        if 'frame_ref' in node:
            fid = node['frame_ref']
            name = labels.get(fid, fid)
            return name + ('(' + describe(contents[fid]) + ')' if fid in contents else '')
        return node.get('operator', 'value') + '(' + ', '.join(describe(c) for c in node.get('operands', ())) + ')'
    pending=deque(modifiers);deferred=[];progress=False
    while pending:
        modifier=pending.popleft()
        options, operations = [], {}
        for path, target in positions(tree, contents):
            source_index = modifier.get('source_index')
            origin=set(modifier.get('source_refs',()))
            if origin:
                if not expanded_leaves(target,contents)&origin:continue
            elif source_index is not None:
                operands = [key for kind, key in path if kind == 'operand']
                # A local modifier can remain in its own conjunct or contain
                # the coordinated subtree. It cannot migrate to another one.
                if operands and operands[0] != source_index:
                    continue
            if modifier.get('allowed_paths') is not None and path not in modifier['allowed_paths']:
                continue
            cid = 'scope-edge:' + digest([modifier['id'], tree, contents, path, 'WRAP'])
            operations[cid] = (path, target, False)
            shared_scope = source_index is not None and (target.get('operator')=='AND' or not any(kind == 'operand' for kind, key in path))
            options.append({'candidate_id': cid, 'label': modifier['label'] + ' applies to ' + describe(target) +
                            ('; SHARED scope: use when compatible with every conjunct and no contextual separator is supported' if shared_scope else '')})
            # Parallel predicates about the SAME content; not AND of events.
            if 'frame_ref' in target and target['frame_ref'] in contents and modifier.get('allow_shared', False):
                cid = 'scope-edge:' + digest([modifier['id'], tree, contents, path, 'SHARED_CONTENT'])
                operations[cid] = (path, target, True)
                options.append({'candidate_id': cid, 'label': modifier['label'] + ' and ' + labels.get(target['frame_ref'], target['frame_ref']) +
                                ' independently describe the same content ' + describe(contents[target['frame_ref']])})
            if len(options)>cfg['max_candidates']:
                state.diag('COMPONENT_SEARCH_INCOMPLETE',region.region_id)
                return None
        if not options or len(options) > cfg['max_candidates']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE' if options else 'NO_GROUNDED_CANDIDATE', region.region_id)
            return None
        key = region.region_id + '|scope-slot:' + digest([modifier, tree, contents, options])
        previous = state.decisions.get(key)
        selected = previous.selected[0] if previous and previous.outcome == 'RESOLVED' and len(previous.selected) == 1 else None
        if selected is None:
            selected = _probe(state, selector, release, key, 'modifier_scope', options,
                              state.text[slice(*region.source_range)], region.source_range,
                              question='Choose the immediate content of this modifier. Existing children are already parsed; '
                              'do not change their identities or infer factivity. Compare only the scope edges listed. '
                              'Use the source context to distinguish nesting from descriptions of the same content. '+
                              ('Declared SHARED_COORDINATION_V1 preference: ask what wording or context would separate these actions. '
                               'If the modifier is compatible with all conjuncts and no separator is supported, choose SHARED scope. '
                               'Mere logical possibility of a local reading is not a reason to abstain. '
                               'If there IS a contrast, incompatible circumstance, quotation or semantic scope barrier, choose the licensed local scope; '
                               'if applicability itself is unknown, answer ?. Shared scope does not assert simultaneity.'
                               if source_index is not None else ''))
        state.syntax_trace.append({'kind': 'SCOPE_SLOT', 'decision_ref': key,
                                   'modifier_ref': modifier['id'], 'alternatives': options, 'selected': selected})
        if selected not in operations:
            deferred.append(modifier)
            if not pending:
                if not progress:
                    state.syntax_trace.append({'kind':'SCOPE_RESIDUAL','region_ref':region.region_id,
                        'pending_modifier_refs':[m['id'] for m in deferred],
                        'fixed_decision_refs':list(decisions),'tree':deepcopy(tree),'contents':deepcopy(contents)})
                    state.diag('COMPONENT_NOMINAL_SELECTION_UNRESOLVED', region.region_id)
                    return None
                pending,deferred=deque(deferred),[];progress=False
            continue
        path, target, shared = operations[selected]
        if source_index is not None and not any(kind == 'operand' for kind, key in path):
            from .state import Ground
            decision = state.decisions[key]
            if not any(h.get('kind')=='SCOPE_PREFERENCE' and h.get('rule_id')=='SHARED_COORDINATION_V1'
                       and h.get('selected')==selected for h in decision.history):
                decision.grounds.append(Ground('R', 'SHARED_COORDINATION_V1: compatible coordination without supported separator', selected))
                decision.history.append({'kind':'SCOPE_PREFERENCE','rule_id':'SHARED_COORDINATION_V1',
                                         'selected':selected,'unselected':[o['candidate_id'] for o in options if o['candidate_id']!=selected],
                                         'reason':'PREFERRED_INTERPRETATION_NOT_LOGICAL_EXCLUSION'})
            # Freeze the policy evidence together with the model/clarification.
            from dataclasses import asdict
            state.component_probe_records[key]['decision'] = asdict(decision)
        child = contents[target['frame_ref']] if shared else target
        contents[modifier['id']] = deepcopy(child)
        replacement = reference(modifier['id'])
        if shared:
            replacement = {'operator': 'AND', 'operands': [target, replacement]}
        tree = replace(tree, contents, path, replacement)
        decisions.append(key);progress=True
        if not pending and deferred:
            pending,deferred=deque(deferred),[];progress=False
    return tree, contents, decisions


def modifier_shape(tree, contents, ids, base):
    """Lower selected slots to the existing nominal materializer's shape."""
    if tree == reference(base):
        return None
    if 'frame_ref' in tree:
        fid = tree['frame_ref']
        return ('MOD', ids.index(fid), modifier_shape(contents[fid], contents, ids, base))
    return ('AND', tuple(modifier_shape(c, contents, ids, base) for c in tree['operands']))
