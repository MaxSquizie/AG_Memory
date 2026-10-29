"""Read existing source structure for reference probes; never infer new roles."""
from .canonical_ledger import digest
from .composition_tree import forests, slots, embedded
from .probe_wording import role


def signature(state):
    # This is deliberately independent of resolved lexical senses/reference
    # results. Those are not permissions to change the accepted source roles.
    return digest([state.source_uid,state.interpretation_version,state.text,
        state.structural_closed,state.logical_roots,
        [(t.token_id,t.span,t.start,t.end) for t in state.evidence],
        [(f.frame_id,f.predicate_token_ref,f.source_range,f.argument_token_refs,{k:f.semantic.get(k) for k in (
            'proposed_roles','proposition_args','nominal_args','component_scope_tree','operator_forest',
            'structural_unresolved','structural_rejection','discourse_scope','partial_composition',
            'component_child','coordination_owner','lexical_units','region','explicit_region',
            'bound_arguments','implicit_arguments','shared_implicit_arguments')}) for f in state.frames]])


OPERATORS={'NOT':'negation of', 'AND':'conjunction of', 'OR':'inclusive alternatives',
    'XOR':'exclusive alternatives', 'IMPLIES':'condition followed by consequence',
    'POSSIBLE':'possibility of', 'NECESSARY':'necessity of',
    'COUNTERFACTUAL':'counterfactual condition followed by consequence',
    'ASSOCIATION':'association of', 'FORALL':'for every bound participant: binder then body',
    'EXISTS':'there exists a bound participant: binder then body',
    'AT_LEAST_N':'at least the stated count: count, binder, then body',
    'AT_MOST_N':'at most the stated count: count, binder, then body',
    'EXACTLY_N':'exactly the stated count: count, binder, then body'}


def describe(state):
    evidence={t.token_id:t for t in state.evidence}
    frames={f.frame_id:f for f in state.frames}
    missing=[]
    if not state.structural_closed:missing.append('STRUCTURE_NOT_SEALED')
    def time_text(value):
        if not value:return ''
        kinds={'POINT':'at the stated instant','CONTINUOUS':'throughout the stated interval',
               'EXISTENTIAL':'at some time within the stated interval'}
        if value.get('kind') not in kinds:
            missing.append('TEMPORAL_SCOPE_VIEW_UNSUPPORTED');return '[unrepresented temporal constraint]'
        from datetime import datetime, timezone
        def stamp(v):
            if v is None:return 'unknown'
            try:return datetime.fromtimestamp(v,timezone.utc).isoformat()
            except (ValueError,TypeError,OverflowError,OSError):
                missing.append('TEMPORAL_SCOPE_VIEW_UNSUPPORTED');return '[unrepresented time]'
        words=[kinds[value['kind']]]
        for e in value.get('expressions',()):
            if e.get('raw'):words.append('source time wording «'+e['raw']+'»')
        if 'point' in value:words.append('instant '+stamp(value['point']))
        if 'lo' in value or 'hi' in value:words.append('interval '+stamp(value.get('lo'))+' to '+stamp(value.get('hi')))
        if value.get('points'):words.append('instants '+', '.join(stamp(v) for v in value['points']))
        return '; '.join(words)
    def occurrence(ref):
        t=evidence.get(ref)
        if t is None:
            missing.append('STRUCTURE_ANCHOR_MISSING');return '[unavailable occurrence]'
        return '«'+t.span+'» at characters '+str(t.start)+':'+str(t.end)
    def frame_text(fid,active):
        f=frames.get(fid)
        if f is None or fid in active:
            missing.append('STRUCTURE_REFERENCE_UNAVAILABLE');return '[unavailable structure]'
        sem=f.semantic
        if sem.get('structural_unresolved') or sem.get('structural_rejection'):
            return occurrence(f.predicate_token_ref)+' [structure unresolved; no established role assignment]'
        parts=[]
        for tid,r in sem.get('proposed_roles',{}).items():
            parts.append(role(r)+' = '+occurrence(tid))
        for tid,variable in sem.get('bound_arguments',{}).items():
            parts.append(occurrence(tid)+' is bound variable '+str(variable)+'; not an independently named individual')
        for r in sem.get('implicit_arguments',{}):parts.append(role(r)+' omitted; identity not inferred here')
        for r in sem.get('shared_implicit_arguments',{}):parts.append(role(r)+' shared with the governing predicate')
        temporal=time_text(sem.get('explicit_region') or sem.get('region'))
        if temporal:parts.append('time of this predicate: '+temporal)
        for slot in slots(f):
            if slot.kind=='NOMINAL':
                owner=occurrence(slot.metadata.get('host_token_ref'))
                slot_label='nominal description of '+owner
                if slot.metadata.get('host_role'):slot_label+='; host fills '+role(slot.metadata['host_role'])+' in that description'
            else:slot_label=role(slot.name)
            parts.append(slot_label+' nested content ('+slot.metadata.get('attitude','assertion status not established')+') = '+render(slot.tree,active|{fid}))
        scope=sem.get('discourse_scope',{})
        if scope:
            parts.append('utterance status: '+str(scope.get('speech_act','UNKNOWN')))
            if scope.get('quoted'):parts.append('inside quoted content')
            for field,title in (('speaker_mention','established speaker'),('addressee_mention','established addressee')):
                if scope.get(field):parts.append(title+' = '+occurrence(scope[field]))
        return occurrence(f.predicate_token_ref)+' ['+'; '.join(parts)+']'
    def render_content(tree,active):
        if 'frame_ref' in tree:return frame_text(tree['frame_ref'],active)
        if 'choice_ref' in tree:
            return 'Retained alternative structures ('+' | '.join(render(c,active) for c in tree.get('alternatives',()))+')'
        if 'bound_var' in tree:
            return 'bound variable '+str(tree['bound_var'])
        if 'count_literal' in tree:return 'count '+str(tree['count_literal'])
        name=OPERATORS.get(tree.get('operator'))
        if name is None:
            missing.append('SCOPE_VIEW_UNSUPPORTED');return '[scope not represented]'
        return name+' ('+'; '.join(render(c,active) for c in tree.get('operands',()))+')'
    def render(tree,active=frozenset()):
        text=render_content(tree,active)
        temporal=time_text(tree.get('region'))
        return ('time constraint on this WHOLE expression ('+temporal+'): '+text) if temporal else text
    trees=forests(state.frames,state.logical_roots)
    children=embedded(state.frames,trees)
    trees += [{'frame_ref':f.frame_id} for f in state.frames if f.frame_id not in children
              and not f.semantic.get('component_child') and not f.semantic.get('coordination_owner')
              and not f.semantic.get('structural_rejection')]
    lines=list(dict.fromkeys(render(tree) for tree in trees))
    if not lines:missing.append('STRUCTURE_MISSING')
    return '\n'.join(lines),tuple(dict.fromkeys(missing))


def inputs(state,target_refs,options):
    from .probe_inputs import ProbeInputs
    established,missing=describe(state)
    for tid in target_refs:
        owners=[f for f in state.frames if tid in f.argument_token_refs or
                tid in f.semantic.get('lexical_units',{}) or tid in f.semantic.get('proposed_roles',{})
                or tid==f.predicate_token_ref]
        if not owners or not any(not f.semantic.get('structural_unresolved') and
                                 not f.semantic.get('structural_rejection') for f in owners):
            missing=(*missing,'TARGET_STRUCTURE_UNAVAILABLE')
    # Preserve the original envelope, including material outside child spans.
    # The ordinary prompt budget may stop this task; it must not truncate it.
    return ProbeInputs('REFERENCE',tuple(target_refs),(0,len(state.text)),state.text,
                       tuple(o['candidate_id'] for o in options),established,signature(state),missing)


def implicit_inputs(state,frame,role,options):
    from dataclasses import replace
    return replace(inputs(state,(frame.predicate_token_ref,),options),family='IMPLICIT_ARGUMENT',
                   owner_ref=frame.frame_id,requested_role=role)
