"""Addressed T2 nominal slots, independent of adjacency and lexical lists.

Heads and function material are selected separately. Discontinuous material
keeps exact occurrence refs. Quantities remain source expressions, not numbers.
"""
from .canonical_ledger import digest
from .structural_tasks import choose,source_set


def rows(state,tokens,kind=None):
    allowed={t.token_id for t in tokens}
    unique={}
    for row in state.syntax_trace:
        if (row.get('kind')=='NOMINAL_FUNCTION' and not row.get('superseded') and set(row['anchor_refs'])<=allowed
                and (kind is None or row['function']==kind)):
            unique[row['unit_ref']]=row
    return list(unique.values())


def prepared(state,tokens):
    from .function_inventory import identity
    kind,refs,signature=identity(state,'NOMINAL',tokens)
    return any(r.get('inventory_kind')==kind and r.get('inventory_tokens')==list(refs)
               and r.get('inventory_complete')
               and not r.get('superseded') for r in state.syntax_trace)


def prepare(state,release,selector,region,tokens,cfg):
    from .function_inventory import begin,complete
    inventory=begin(state,'NOMINAL',tokens,cfg.get('_task_constraints'))
    if inventory is None:return True
    used=set();relation_heads=set()
    while True:
        selected=choose(state,release,selector,region,cfg,'nominal_function',[
            {'candidate_id':'DONE','label':'No further nominal relation, referential determiner or quantity expression'},
            {'candidate_id':'RELATION','label':'An adposition or multiword relational unit links a nominal to another participant or event'},
            {'candidate_id':'REFERENCE','label':'An expression identifies a nominal by referring to context or a previous mention'},
            {'candidate_id':'QUANTITY','label':'An expression specifies a nominal group quantity; retain it symbolically'}],
            'Which remaining nominal function occurs here? Ordinary names and descriptive adjectives alone do not need these slots. '
            'Already assigned function words: «'+' '.join(t.span for t in tokens if t.token_id in used)+'».')
        if not selected:return False
        kind=selected[0]['candidate_id']
        if kind=='DONE':
            state.syntax_trace.append({'kind':'NOMINAL_FUNCTION_DOMAIN','token_refs':[t.token_id for t in tokens],
                'decision_ref':selected[1]['decision_ref'],'search_complete':True,**inventory})
            complete(state,inventory)
            return True
        head=choose(state,release,selector,region,cfg,'nominal_function_head',[
            {'candidate_id':t.token_id,'head_ref':t.token_id,'label':'Nominal head «'+t.span+'» @'+str(t.start)}
            for t in tokens if t.token_id not in used and any(c.isalnum() for c in t.span)],
            kind+': which occurrence is the nominal head receiving this function?')
        if not head:return False
        hid=head[0]['head_ref']
        if kind=='RELATION' and hid in relation_heads:
            state.diag('NOMINAL_RELATION_MULTIPLE_EDGES_UNRESOLVED',region.region_id)
            return False
        if kind=='RELATION':relation_heads.add(hid)
        material=source_set(state,release,selector,region,tokens,cfg,'nominal_function_source',
            kind+': select the function expression only, excluding the nominal head and ordinary descriptive modifiers.',exclude=used|{hid})
        if not material:return False
        owned,proofs=material;refs=[t.token_id for t in owned]
        allrefs=[t.token_id for t in tokens if t.token_id in {*refs,hid}]
        row={**inventory,'kind':'NOMINAL_FUNCTION','unit_ref':'nominal-function:'+digest([region.region_id,kind,hid,refs]),
             'function':kind,'head_ref':hid,'function_refs':refs,'anchor_refs':allrefs,
             'source_range':[min(t.start for t in tokens if t.token_id in allrefs),max(t.end for t in tokens if t.token_id in allrefs)],
             'proofs':[selected[1],head[1],*proofs],'decision_ref':selected[1]['decision_ref']}
        if kind=='REFERENCE':
            identity=choose(state,release,selector,region,cfg,'nominal_identity_function',[
                {'candidate_id':'CONTEXTUAL','label':'Identify the nominal from context; identity with a prior mention is not explicitly required'},
                {'candidate_id':'SAME','label':'The source explicitly requires the same referent as a prior mention'}],
                'Reference expression: «'+' '.join(t.span for t in owned)+'». What identity constraint is stated?')
            if not identity:return False
            row['identity_constraint']=identity[0]['candidate_id'];row['proofs'].append(identity[1])
        if kind=='QUANTITY':
            case=choose(state,release,selector,region,cfg,'nominal_external_case',[
                {'candidate_id':c,'label':label} for c,label in [('nom','Subject form'),('gen','Genitive form'),
                ('dat','Dative form'),('acc','Direct object form'),('abl','Instrumental form'),('ins','Instrumental form (alternate tag)'),('loc','Prepositional/locative form'),('voc','Address form')]],
                'Which external grammatical case does this whole quantity group take here? Its inner noun can have a different case.')
            if not case:return False
            row['external_case']=case[0]['candidate_id'];row['case_proof']=case[1]
        state.syntax_trace.append(row);used.update(refs)


def prepositions(state,tokens,excluded=()):
    from .state import MorphVariant
    from .morphology_domain import offer,license_use
    from .component_policy import _morph
    by_id={t.token_id:t for t in tokens};out={}
    for row in rows(state,tokens,'RELATION'):
        if set(row['anchor_refs'])&set(excluded):continue
        head=row['head_ref'];refs=row['function_refs'];marker=by_id[refs[0]]
        if head in out:raise ValueError('NOMINAL_RELATION_MULTIPLE_EDGES_UNRESOLVED')
        variants=[v for v in marker.variants if v.pos=='PREP'] if len(refs)==1 else []
        if not variants:
            variants=offer(state,marker,[MorphVariant(' '.join(by_id[r].span for r in refs),'PREP',origin='CONTEXTUAL')],
                           'RELATION_FUNCTION',refs)
            for v in variants:license_use(state,marker.token_id,_morph(v),row['decision_ref'],'RELATION')
        out[head]={'token_ref':marker.token_id,'head_ref':head,'variants':variants,
            'anchor_refs':row['anchor_refs'],'function_refs':refs,'source_range':row['source_range'],
            'ambiguous_pos':True,'structural_license':row['proofs']}
    return out
