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
    used=set();used_by_kind={k:set() for k in ('RELATION','REFERENCE','QUANTITY')};relation_heads=set()
    while True:
        selected=choose(state,release,selector,region,cfg,'nominal_function',[
            {'candidate_id':'RELATION','label':'An adposition or multiword relational unit: words introducing a noun/pronoun and linking it to an action or another noun (place, destination, origin, instrument, possession or another relation)'},
            {'candidate_id':'REFERENCE','label':'An expression points to which person/thing is meant, using context or an earlier mention'},
            {'candidate_id':'QUANTITY','label':'An expression says how many or how much of a noun group; keep its wording'}],
            'Look for words in THIS target that introduce or specify a noun/pronoun. '
            'A preposition connecting a place to a verb counts as RELATION, even when the verb already has a place role. '
            'Choose the function of the FIRST remaining such expression, not all functions anywhere in the sentence. '
            'A name by itself or an ordinary descriptive adjective does not count. '
            'Already assigned functions (do not select the same function of the same occurrence again): '+
            '; '.join(k+': «'+' '.join(t.span for t in tokens if t.token_id in refs)+'»' for k,refs in used_by_kind.items())+'.',
            empty={'candidate_id':'DONE','label':'no further nominal relation, referential determiner or quantity expression'})
        if not selected:return False
        kind=selected[0]['candidate_id']
        if kind=='DONE':
            state.syntax_trace.append({'kind':'NOMINAL_FUNCTION_DOMAIN','token_refs':[t.token_id for t in tokens],
                'decision_ref':selected[1]['decision_ref'],'search_complete':True,**inventory})
            complete(state,inventory)
            return True
        material=source_set(state,release,selector,region,tokens,cfg,'nominal_function_source',
            kind+': select ONLY the connecting/determining/quantity expression. '
            'Exclude a separate nominal head and unrelated modifiers. Include a word that itself BOTH expresses this function and stands for its nominal bearer.',exclude=used_by_kind[kind])
        if not material:return False
        owned,proofs=material;refs=[t.token_id for t in owned]
        expression=' '.join(t.span for t in owned)
        head=choose(state,release,selector,region,cfg,'nominal_function_head',[
            {'candidate_id':t.token_id,'head_ref':t.token_id,'shared_function':t.token_id in refs,
             'label':'Nominal head «'+t.span+'» @'+str(t.start)+(' (this occurrence also carries the selected function)' if t.token_id in refs else '')}
            for t in tokens if (kind!='RELATION' or t.token_id not in refs) and any(c.isalnum() for c in t.span)],
            kind+': selected function expression is «'+expression+'». '
            +('Which noun/pronoun is its complement: the entity/place introduced BY this expression, not the outside predicate or participant it attaches to? '
              if kind=='RELATION' else 'Which noun/pronoun is determined or counted by this expression? ')+
            'Select the nominal bearer. A reference or quantity word may itself be that bearer; choose it only if the text supplies no separate head for this expression.')
        if not head:return False
        hid=head[0]['head_ref']
        if kind=='RELATION' and hid in relation_heads:
            state.diag('NOMINAL_RELATION_MULTIPLE_EDGES_UNRESOLVED',region.region_id)
            return False
        if kind=='RELATION':relation_heads.add(hid)
        allrefs=[t.token_id for t in tokens if t.token_id in {*refs,hid}]
        row={**inventory,'kind':'NOMINAL_FUNCTION','unit_ref':'nominal-function:'+digest([region.region_id,kind,hid,refs]),
             'function':kind,'head_ref':hid,'function_refs':refs,'anchor_refs':allrefs,
             'source_range':[min(t.start for t in tokens if t.token_id in allrefs),max(t.end for t in tokens if t.token_id in allrefs)],
             'shared_function':bool(head[0].get('shared_function')), 'head_proof':head[1],
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
                {'candidate_id':c,'label':label} for c,label in [('nom','Nominative case'),('gen','Genitive case'),
                ('dat','Dative case'),('acc','Accusative case'),('abl','Instrumental case'),('loc','Prepositional/locative case'),('voc','Vocative case')]],
                'Which external grammatical case does this whole quantity group take here? Its inner noun can have a different case.')
            if not case:return False
            row['external_case']=case[0]['candidate_id'];row['case_proof']=case[1]
        state.syntax_trace.append(row);used.update(refs);used_by_kind[kind].update(refs)


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


def shared_nominal_readings(state,token,source):
    """T2 head proof licenses nominal use of a shared source occurrence.

    Keep attested nominal readings. Otherwise nominal function supplies no
    dictionary lemma or paradigm: those features stay unknown until consumed.
    """
    from .state import MorphVariant
    from .component_policy import _morph
    from .morphology_domain import offer,license_use
    values=tuple(v for v in token.variants if v.pos in {'NOUN','NPRO'})
    if values:return values
    proof=source['head_proof']
    values=offer(state,token,[MorphVariant(token.span.casefold(),'NOUN',origin='CONTEXTUAL')],
                 'SHARED_NOMINAL_FUNCTION',source['function_refs'])
    for value in values:license_use(state,token.token_id,_morph(value),proof['decision_ref'],proof['candidate_id'])
    return tuple(values)
