"""Explicit bounded dictionary inflection repair after local agreement failure."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import policy,_morph,_features,compatible
from .component_probe import _probe


def distance(a,b):
    row=list(range(len(b)+1))
    for i,x in enumerate(a,1):
        new=[i]
        for j,y in enumerate(b,1):new.append(min(new[-1]+1,row[j]+1,row[j-1]+(x!=y)))
        row=new
    return row[-1]


def resolve(state,release,selector,morph,*,areas=None):
    cfg=policy(release) or {};rule=cfg.get('agreement_recovery')
    if not rule:return
    from .pipeline import MorphProvider
    provider=morph or MorphProvider()
    if not callable(getattr(provider,'inflect',None)):return
    by_id={e.token_id:e for e in state.evidence}
    if areas is None:
        areas=[(r,[by_id[t] for t in r.token_refs]) for r in state.region_forest.regions if r.kind=='SENTENCE']
    for region,tokens in areas:
        for i,token in enumerate(tokens):
            originals=[v for v in token.variants if v.pos=='ADJF' and v.origin=='DICTIONARY']
            if not originals:continue
            j=i+1
            while j<len(tokens) and any(v.pos in {'ADJF','PRTF'} for v in tokens[j].variants):j+=1
            if j>=len(tokens):continue
            head=tokens[j];nouns=[v for v in head.variants if v.pos=='NOUN' and v.origin=='DICTIONARY']
            if not nouns or any(v.cases&n.cases and compatible(_features(v),_features(n)) for v in originals for n in nouns):continue
            candidates={}
            for lemma in sorted({v.lemma for v in originals}):
                for n in nouns:
                    for case in sorted(n.cases):
                        for surface,v in provider.inflect(token.span,lemma,{'case':case,'number':n.number,'gender':n.gender}):
                            if not 0<distance(token.span.casefold(),surface)<=rule['max_edits']:continue
                            if not v.cases&n.cases or not compatible(_features(v),_features(n)):continue
                            cid=digest([surface,{k:x for k,x in _morph(v).items() if k!='score'}])
                            candidates[cid]=(surface,v)
            if not candidates:continue
            from .morphology_domain import scope_fields,clean
            scope=scope_fields(state)
            key='agreement-recovery:'+token.token_id+(':'+scope['task_scope'] if scope else '')
            if len(candidates)+1>cfg['max_candidates'] or region.source_range[1]-region.source_range[0]>cfg['context_chars']:
                state.diag('LEXICAL_RECOVERY_INCOMPLETE',key);continue
            from .probe_wording import reading as reading_text
            choices=[{'candidate_id':'KEEP','label':'Keep «'+token.span+'» as written; no licensed correction established'}]
            choices += [{'candidate_id':cid,'label':'Explicit inflection correction «'+token.span+'» → «'+surface+'»; same dictionary lexeme; '+reading_text(_morph(v))} for cid,(surface,v) in candidates.items()]
            from .component_source import view,probe_context
            context,target=probe_context(state,region,cfg,view(state,region,tokens))
            chosen=_probe(state,selector,release,key,'lexical_recovery',choices,context,region.source_range,
                question=target+'Is a grammatical inflection error supported for «'+token.span+'» @'+str(token.start)+'? The proposed head is «'+head.span+'» @'+str(head.start)+'. '
                'Edit distance merely proposes candidates, not proof. Keep the original if a legitimate uncorrected reading remains; answer ? if uncertain. Do not alter names or infer a new lexical meaning.', target_refs=(token.token_id,))
            row={'kind':'AGREEMENT_RECOVERY',**scope,'token_ref':token.token_id,'head_ref':head.token_id,
                'original_variants':[_morph(v) for v in token.variants],'options':choices,'selected':chosen}
            state.syntax_trace.append(row)
            if chosen not in candidates:continue
            surface,v=candidates[chosen]
            token.lexical_recovery={'surface':surface,'source_surface':token.span,'decision_ref':key,
                'original_variants':[_morph(x) for x in token.variants]}
            token.variants=(replace(v,origin='RECOVERED',evidence_refs=(*v.evidence_refs,head.token_id,key)),)
            token.lemma=v.lemma;token.pos=v.pos;token.cases=v.cases;token.lex_status='RECOVERY_SELECTED'
            row.update(recovered_reading=clean(token.variants[0]),lexical_recovery=token.lexical_recovery)
