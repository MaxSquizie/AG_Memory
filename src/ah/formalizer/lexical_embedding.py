"""Optional learned ordering of a CLOSED lexical domain after structural seal.

Similarity is not a calibrated probability of sense identity. This experiment
retains every candidate and OPEN; decisions still use the bounded selector.
Receipts record scores so replay never needs the embedding server or its cache.
"""
from collections import OrderedDict
import json
import math
from threading import RLock
from ah.diagnostics import runtime_trace

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
        with runtime_trace.span('EMBEDDING_VECTORS', model_key=self.model_key,
                batch_size=self.batch_size, cache_limit=self.cache_size) as outcome:
            with self.lock:
                vectors = self._vectors(texts)
                outcome.update(status='READY', vector_count=len(vectors),
                    dimension=len(vectors[0]) if vectors else None,
                    normalization='L2_UNIT', cache_entries=len(self.cache))
                return vectors

    def _vectors(self,texts):
        result={text:self.cache[text] for text in texts if text in self.cache}
        missing=list(dict.fromkeys(text for text in texts if text not in result))
        runtime_trace.emit('embedding_cache_lookup', model_key=self.model_key,
            status='HIT' if not missing else 'PARTIAL' if result else 'MISS',
            hit_texts=list(result), missing_count=len(missing), cache_entries=len(self.cache))
        for start in range(0,len(missing),self.batch_size):
            batch=missing[start:start+self.batch_size]
            with runtime_trace.span('EMBEDDING_BATCH', model_key=self.model_key,
                    batch_index=start//self.batch_size,
                    client_type=type(self.client).__name__) as outcome:
                runtime_trace.emit('embedding_request', model_key=self.model_key,
                    texts=batch, text_count=len(batch))
                vectors=self.client.embed(batch)
                # Shape metadata describes the actual response before validation;
                # raw high-dimensional vectors are not needed to replay scores.
                _trace_response(vectors, self.model_key)
                if len(vectors)!=len(batch):raise ValueError('embedding count mismatch')
                result.update(zip(batch,(self.unit(v) for v in vectors)))
                outcome.update(status='NORMALIZED', vector_count=len(batch),
                    dimensions=[len(result[text]) for text in batch], normalization='L2_UNIT',
                    dimension_validation_pending=True)
        if len({len(v) for v in result.values()})!=1:raise ValueError('embedding dimension mismatch')
        for text in texts:
            self.cache[text]=result[text];self.cache.move_to_end(text)
        evicted = []
        while len(self.cache)>self.cache_size:
            text, _ = self.cache.popitem(last=False)
            evicted.append(text)
        if evicted:
            runtime_trace.emit('embedding_cache_evicted', model_key=self.model_key,
                texts=evicted, cache_entries=len(self.cache))
        return [result[text] for text in texts]

    def rank(self,selector,release,key,query,options):
        with runtime_trace.bind(entity_id=key, decision_ref=key):
            with runtime_trace.span('LEXICAL_EMBEDDING_RANK', model_key=self.model_key,
                    algorithm=VERSION) as outcome:
                try:
                    ordered, scores = self._rank(selector,release,key,query,options)
                except ProviderUnavailable as exc:
                    outcome.update(status='UNAVAILABLE', reason=runtime_trace.error_text(exc))
                    raise
                except IntegrityError as exc:
                    outcome.update(status='REJECTED', reason=runtime_trace.error_text(exc))
                    raise
                else:
                    outcome.update(status='RANKED', scores=scores,
                        ordered_candidates=[option['candidate_id'] for option in ordered],
                        automatic_selection=False, probe_required=True)
                    return ordered, scores

    def _rank(self,selector,release,key,query,options):
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


def _trace_response(vectors, model_key):
    if not runtime_trace.enabled():
        return
    try:
        sequence = isinstance(vectors, (list, tuple))
        runtime_trace.emit('embedding_response', model_key=model_key, status='RECEIVED',
            response_type=type(vectors).__name__, vector_count=len(vectors) if sequence else None,
            dimensions=[len(vector) if isinstance(vector, (list, tuple)) else None
                        for vector in vectors] if sequence else None,
            validation_pending=True, raw_vectors_recorded=False)
    except Exception as exc:
        runtime_trace.emit('trace_capture_failed', observer='embedding_response',
            status='ERROR', reason=runtime_trace.error_text(exc))


def order(state,selector,release,frame,options,context):
    ranker=getattr(selector,'lexical_ranker',None)
    if ranker is None:
        runtime_trace.emit('embedding_order_skipped',
            status='SKIPPED', reason='RANKER_NOT_CONFIGURED')
        return options
    if not state.structural_closed:
        runtime_trace.emit('embedding_order_rejected',
            status='REJECTED', reason='STRUCTURAL_SEAL_REQUIRED')
        raise ValueError('embedding lexical selection before structural seal')
    specs=frame.semantic['candidate_specs']
    known=[o for o in options if specs[o['candidate_id']]['sense_kind']=='KNOWN']
    other=[o for o in options if specs[o['candidate_id']]['sense_kind']!='KNOWN']
    if not known:
        runtime_trace.emit('embedding_order_skipped',
            status='SKIPPED', reason='NO_KNOWN_SENSE')
        return options
    key=frame.frame_id+'|predicate_value'
    row={'kind':'LEXICAL_EMBEDDING_RANKING','decision_ref':key,'model_key':ranker.model_key,
         'algorithm':VERSION,'input_candidates':[o['candidate_id'] for o in options],
         'automatic_selection':False,'probe_required':True}
    if len({specs[o['candidate_id']]['sense_id'] for o in known})<2:
        row.update(status='SKIPPED',reason='ONE_KNOWN_SENSE_NO_ORDERING_GAIN',
                   ordered_candidates=row['input_candidates'])
        state.syntax_trace.append(row)
        runtime_trace.emit('embedding_order_result', entity_id=key, **row)
        return options
    try:
        documents=[{'candidate_id':o['candidate_id'],'label':specs[o['candidate_id']]['label']} for o in known]
        ranked,scores=ranker.rank(selector,release,key,
            'Meaning of predicate «'+frame.anchor_span+'» in this selected clause: '+context,documents)
    except ProviderUnavailable as exc:
        row.update(status='UNAVAILABLE',reason=str(exc),ordered_candidates=row['input_candidates'])
        state.syntax_trace.append(row)
        runtime_trace.emit('embedding_order_result', entity_id=key, **row)
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
    runtime_trace.emit('embedding_order_result', entity_id=key, **row)
    return ordered
