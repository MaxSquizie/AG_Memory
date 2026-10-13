"""Select source-asserted content of existing trees, never generate new trees."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_probe import _probe


def enabled(release):
    return release.entries('ProposalPolicy')[0].get('composition',{}).get('source_assertions')=='BOUNDED_SOURCE_V1'


def leaves(tree):
    if 'frame_ref' in tree:return {tree['frame_ref']}
    return set().union(*(leaves(t) for t in tree.get('operands',())))


def resolve(state,release,selector):
    if not enabled(release):return
    frames={f.frame_id:f for f in state.frames}
    state.observation['source_assertions']=[]
    children=set()
    for f in frames.values():
        for arg in f.semantic.get('proposition_args',{}).values():
            children.update(leaves(arg.get('tree') or {'frame_ref':arg['frame_ref']}))
        for arg in f.semantic.get('nominal_args',()):
            children.update(leaves(arg.get('tree') or {'frame_ref':arg['frame_ref']}))
    forests=list(state.logical_roots)
    for f in frames.values():
        forests.extend(f.semantic.get('operator_forest',()))
        if f.semantic.get('component_scope_tree') and not f.semantic.get('component_child') and not f.semantic.get('structural_unresolved'):forests.append(f.semantic['component_scope_tree'])
    for tree in forests:children.update(leaves(tree))
    cfg=release.entries('ProposalPolicy')[0]['composition']
    visited=set()

    def label(tree):
        if 'frame_ref' in tree:
            f=frames[tree['frame_ref']]
            return '«'+f.anchor_span+'» at '+str(f.source_range)
        return tree.get('operator','literal')+'('+', '.join(label(t) for t in tree.get('operands',()))+')'

    def walk(tree,root,seen,source_range=None):
        if 'frame_ref' not in tree:
            # AND preserves assertion; other operators do not license projection.
            if tree.get('operator')=='AND':
                for child in tree['operands']:walk(child,root,seen,source_range)
            return
        fid=tree['frame_ref']
        if fid in seen:return
        f=frames[fid];sem=f.semantic;d=state.decisions.get(fid+'|predicate_value')
        from .component_policy import rejected
        if not d or d.outcome!='RESOLVED' or rejected(state,f) or sem.get('structural_unresolved') or sem.get('source_blocked') or sem.get('quoted') or sem.get('query_request'):return
        from .native_frontend import _frame_variants
        ev=next(e for e in state.evidence if e.token_id==f.predicate_token_ref)
        if any(v.mood=='imperative' for v in _frame_variants(f,ev)):return
        for role,arg in sem.get('proposition_args',{}).items():
            # No implicit upgrade of known report/hypothetical scope.
            if arg.get('attitude')!='UNKNOWN':continue
            if not any(q.get('kind')=='MODIFIER_SCOPE' for q in sem.get('component_questions',())):continue
            target=arg.get('tree') or {'frame_ref':arg['frame_ref']}
            lo,hi=source_range or frames[root].source_range
            key='source-assertion:'+digest([root,fid,role,target,[lo,hi]])
            if key in visited:continue
            visited.add(key)
            if hi-lo>cfg['context_chars']:
                state.diag('SOURCE_ASSERTION_SCOPE_UNRESOLVED',key);continue
            context=state.text[lo:hi]
            # Negated/questions roots are handled by the operator/goal compiler.
            import re
            if '?' in context or any(re.search(r['pattern'],context,re.I) for r in release.entries('ScopeLexicon') if r.get('operator')=='NOT'):continue
            choice=_probe(state,selector,release,key,'source_assertion',[
                {'candidate_id':'SOURCE_ASSERTED','label':'The source itself asserts '+label(target)+' as occurring/holding, independently of the descriptive modifier.'},
                {'candidate_id':'EMBEDDED','label':'The content is only possible, intended, reported, questioned, denied or otherwise not asserted by the source.'}],
                context,(lo,hi),question='Determine assertion scope, not world truth or lexical identity. Parent modifier: '+label(tree)+'. Target content: '+label(target)+'. '
                'Read the whole supplied utterance. A descriptive companion/location/manner may preserve assertion; possibility, intention and quotation do not. '
                'Select SOURCE_ASSERTED only with positive wording evidence. Otherwise select EMBEDDED or ?; never infer occurrence merely from a typed argument.')
            state.syntax_trace.append({'kind':'SOURCE_ASSERTION_SCOPE','decision_ref':key,'parent_ref':fid,'role':role,'tree':deepcopy(target),'source_range':[lo,hi],'selected':choice})
            if choice=='SOURCE_ASSERTED':
                state.observation['source_assertions'].append({'decision_ref':key,'parent_ref':fid,'role':role,'tree':deepcopy(target),'source_range':[lo,hi]})
                walk(target,root,seen|{fid},(lo,hi))
            elif choice is None:state.diag('SOURCE_ASSERTION_SCOPE_UNRESOLVED',key)

    for f in frames.values():
        if f.frame_id not in children and not f.semantic.get('coordination_owner'):
            walk({'frame_ref':f.frame_id},f.frame_id,set())
    for tree in forests:
        refs=sorted(leaves(tree))
        if refs:
            bounds=(min(frames[r].source_range[0] for r in refs),max(frames[r].source_range[1] for r in refs))
            walk(tree,refs[0],set(),bounds)


def roots(state,release):
    """T5 consumes only checked decisions about existing sealed argument trees."""
    if not enabled(release):return []
    frames={f.frame_id:f for f in state.frames};result=[];seen=set()
    for row in state.observation.get('source_assertions',()):
        d=state.decisions.get(row['decision_ref'])
        f=frames.get(row['parent_ref']);arg=f.semantic.get('proposition_args',{}).get(row['role']) if f else None
        if not d or d.outcome!='RESOLVED' or tuple(d.selected)!=('SOURCE_ASSERTED',) or not arg or arg.get('attitude')!='UNKNOWN':continue
        tree=arg.get('tree') or {'frame_ref':arg['frame_ref']}
        if tree!=row['tree']:raise ValueError('SOURCE_ASSERTION_TREE_CHANGED')
        key=digest(tree)
        if key not in seen:result.append(('source-asserted:'+key,deepcopy(tree)));seen.add(key)
    return result
