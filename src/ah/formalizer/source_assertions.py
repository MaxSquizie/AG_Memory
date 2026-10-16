"""Select source-asserted content of existing trees, never generate new trees."""
from copy import deepcopy
from .canonical_ledger import digest
from .component_probe import _probe


def enabled(release):
    return release.entries('ProposalPolicy')[0].get('composition',{}).get('source_assertions')=='BOUNDED_SOURCE_V1'


from .composition_tree import leaves, forests as composition_forests, embedded


def resolve(state,release,selector):
    if not enabled(release):return
    frames={f.frame_id:f for f in state.frames}
    state.observation['source_assertions']=[]
    forests=composition_forests(state.frames,state.logical_roots)
    children=embedded(state.frames,forests)
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
        if sem.get('discourse_scope',{}).get('speech_act')!='ASSERTION':return
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
            # Operator scope is controlled by walk(), not by finding NOT in
            # the text of a sibling or a quoted child. Question/command source
            # acts remain guarded here and by the ordinary T5 boundary.
            if f.semantic.get('discourse_scope',{}).get('speech_act') in {'QUERY','COMMAND'} or state.observation.get('request_kind') in {'QUERY','COMMAND'}:continue
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
    frames={f.frame_id:f for f in state.frames};result=[];seen=set()
    for row in state.observation.get('source_assertions',()):
        d=state.decisions.get(row['decision_ref'])
        f=frames.get(row['parent_ref']);arg=f.semantic.get('proposition_args',{}).get(row['role']) if f else None
        if not d or d.outcome!='RESOLVED' or tuple(d.selected)!=('SOURCE_ASSERTED',) or not arg or arg.get('attitude')!='UNKNOWN':continue
        tree=arg.get('tree') or {'frame_ref':arg['frame_ref']}
        if tree!=row['tree']:raise ValueError('SOURCE_ASSERTION_TREE_CHANGED')
        key=digest(tree)
        if key not in seen:result.append(('source-asserted:'+key,deepcopy(tree)));seen.add(key)
    # A temporal adjunct construction explicitly preserves its main clause,
    # but never promotes its nominal anchor. Only traverse asserted scope:
    # NOT/OR/modality/report stop this walk, including around a temporal node.
    def project(tree):
        if tree.get('operator')=='AND':
            for child in tree['operands']:project(child)
        projection=tree.get('source_projection')
        if not projection or projection.get('rule_id')!='TEMPORAL_MAIN_CLAUSE':return
        if tree.get('operator') not in {'BEFORE','AFTER','DURING'} or projection.get('operand')!=0:return
        decision=state.decisions.get(projection['decision_ref'])
        if decision is None or decision.outcome!='RESOLVED':return
        child=tree['operands'][0]
        if any(frames[f].semantic.get('query_request') or frames[f].semantic.get('structural_unresolved') for f in leaves(tree)):return
        key=digest(child)
        if key not in seen:
            result.append(('source-asserted:'+key,deepcopy(child)));seen.add(key)
        project(child)
    for tree in composition_forests(state.frames,state.logical_roots):project(tree)
    for _,tree in list(result):project(tree)
    return result
