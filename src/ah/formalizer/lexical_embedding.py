"""Optional learned ordering of a CLOSED lexical domain after structural seal.

Similarity is not a calibrated probability of sense identity. This experiment
retains every candidate and OPEN; decisions still use the bounded selector.
Receipts record scores so replay never needs the embedding server or its cache.
"""
from collections import OrderedDict
import json
import math
from threading import RLock

from .canonical_ledger import digest
from .provider_adapter import ProviderAdapter,BudgetSnapshot,ProviderUnavailable,IntegrityError
from .provider_call_log import ProviderCallLog

VERSION='LEXICAL_EMBEDDING_ORDER_V1'


class LexicalEmbeddingRanker:
    def __init__(self,client,model_key,*,cache_size=2048,batch_size=32):
        if not model_key or cache_size<1 or batch_size<1:raise ValueError('invalid embedding configuration')
        self.client,self.model_key=client,model_key
        self.cache_size,self.batch_size=cache_size,batch_size
        self.cache=OrderedDict()
        self.lock=RLock()

    @staticmethod
    def unit(vector):
        if not isinstance(vector,(list,tuple)) or not vector:raise ValueError('empty embedding')
        if any(isinstance(x,bool) or not isinstance(x,(float,int)) or not math.isfinite(x) for x in vector):
            raise ValueError('invalid embedding values')
        norm=math.sqrt(sum(x*x for x in vector))
        if not math.isfinite(norm) or norm==0:raise ValueError('invalid embedding norm')
        return tuple(x/norm for x in vector)

    def vectors(self,texts):
        with self.lock:return self._vectors(texts)

    def _vectors(self,texts):
        result={text:self.cache[text] for text in texts if text in self.cache}
        missing=list(dict.fromkeys(text for text in texts if text not in result))
        for start in range(0,len(missing),self.batch_size):
            batch=missing[start:start+self.batch_size]
            vectors=self.client.embed(batch)
            if len(vectors)!=len(batch):raise ValueError('embedding count mismatch')
            result.update(zip(batch,(self.unit(v) for v in vectors)))
        if len({len(v) for v in result.values()})!=1:raise ValueError('embedding dimension mismatch')
        for text in texts:
            self.cache[text]=result[text];self.cache.move_to_end(text)
        while len(self.cache)>self.cache_size:self.cache.popitem(last=False)
        return [result[text] for text in texts]

    def rank(self,selector,release,key,query,options):
        request=json.dumps({'release':release.sha256,'query':query,'options':options},ensure_ascii=False,sort_keys=True)
        if len(request)>65536:raise ProviderUnavailable('embedding input limit')
        def transport(payload):
            data=json.loads(payload)
            vectors=self.vectors([data['query'],*(o['label'] for o in data['options'])])
            scores={o['candidate_id']:sum(a*b for a,b in zip(vectors[0],v))
                    for o,v in zip(data['options'],vectors[1:])}
            return json.dumps(scores,sort_keys=True,allow_nan=False)
        adapter=ProviderAdapter(name='LexicalEmbeddingRanking',capabilities=frozenset({'select'}),
            transport=transport,model_key=self.model_key,params_hash=digest(VERSION),
            log=ProviderCallLog(getattr(selector,'journal',None)),budget=BudgetSnapshot(token_limit=65536))
        run_id=getattr(selector,'run_id','lexical')+':embedding:'+key
        raw=adapter.select(request,run_id,ordinal=1)
        try:scores=json.loads(raw)
        except (TypeError,ValueError) as exc:raise IntegrityError('invalid embedding score receipt') from exc
        if (not isinstance(scores,dict) or set(scores)!={o['candidate_id'] for o in options} or
                any(isinstance(v,bool) or not isinstance(v,(float,int)) or not math.isfinite(v) or not -1.000001<=v<=1.000001 for v in scores.values())):
            raise IntegrityError('invalid embedding score receipt')
        ordered=sorted(options,key=lambda o:-scores[o['candidate_id']])
        return ordered,scores


def order(state,selector,release,frame,options,context):
    ranker=getattr(selector,'lexical_ranker',None)
    if ranker is None:return options
    if not state.structural_closed:raise ValueError('embedding lexical selection before structural seal')
    specs=frame.semantic['candidate_specs']
    known=[o for o in options if specs[o['candidate_id']]['sense_kind']=='KNOWN']
    other=[o for o in options if specs[o['candidate_id']]['sense_kind']!='KNOWN']
    if not known:return options
    key=frame.frame_id+'|predicate_value'
    row={'kind':'LEXICAL_EMBEDDING_RANKING','decision_ref':key,'model_key':ranker.model_key,
         'algorithm':VERSION,'input_candidates':[o['candidate_id'] for o in options],
         'automatic_selection':False,'probe_required':True}
    if len({specs[o['candidate_id']]['sense_id'] for o in known})<2:
        row.update(status='SKIPPED',reason='ONE_KNOWN_SENSE_NO_ORDERING_GAIN',
                   ordered_candidates=row['input_candidates'])
        state.syntax_trace.append(row)
        return options
    try:
        documents=[{'candidate_id':o['candidate_id'],'label':specs[o['candidate_id']]['label']} for o in known]
        ranked,scores=ranker.rank(selector,release,key,
            'Meaning of predicate «'+frame.anchor_span+'» in this selected clause: '+context,documents)
    except ProviderUnavailable as exc:
        row.update(status='UNAVAILABLE',reason=str(exc),ordered_candidates=row['input_candidates'])
        state.syntax_trace.append(row)
        return options
    # OPEN expresses absence from the lexicon: it has no semantic prototype to
    # embed. It remains an explicit alternative, never an embedding competitor.
    original={o['candidate_id']:o for o in known}
    ordered=[original[o['candidate_id']] for o in ranked]+other
    values=sorted(scores.values(),reverse=True)
    row.update(status='RANKED',scores=scores,top_score=values[0],
               margin=values[0]-values[1] if len(values)>1 else None,
               ordered_candidates=[o['candidate_id'] for o in ordered],
               reason='UNCALIBRATED_SIMILARITY')
    state.syntax_trace.append(row)
    return ordered
