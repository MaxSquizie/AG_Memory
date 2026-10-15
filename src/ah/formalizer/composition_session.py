"""Run-local recursive dispatcher and addressed context access.

Ephemeral services are never embedded in the sealed IR or serialized state.
Each child cache key includes its owned tokens, morphology and input contract.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import asdict, is_dataclass
from bisect import bisect_left
import json
from .canonical_ledger import digest

_current=ContextVar('formalizer_composition_session',default=None)


class CompositionSession:
    def __init__(self,state,release,reader=None):
        self.state,self.release,self.reader=state,release,reader
        from .composition_tasks import ChildTasks
        self.tasks=ChildTasks(state);self.context={}
        from .composition_sources import CompositionSources
        self.sources=CompositionSources(state,release)
        self.evidence=sorted(state.evidence,key=lambda e:e.start)
        self.starts=[e.start for e in self.evidence]

    def child(self,key,compute):
        return self.tasks.child(key,compute)

    def memory(self,slot,options,source_range,cfg):
        if self.reader is None or len(options)<2:return ''
        # This reader returns the addressed active context, not a different
        # answer per candidate ordering. Reuse it throughout the same area.
        from .context_proofs import compile_goals
        evidence=[e for e in self.evidence[bisect_left(self.starts,source_range[0]):bisect_left(self.starts,source_range[1])]
                  if source_range[0]<=e.start and e.end<=source_range[1]]
        try:goals=compile_goals(self.release,evidence,options,cfg['max_candidates'])
        except ValueError as exc:
            from .attention_context import ContextReadError
            raise ContextReadError('COMPOSITION_GOAL_SEARCH_INCOMPLETE') from exc
        key=digest([source_range,goals,self.tasks.feedback])
        if key not in self.context:
            request={'kind':'STRUCTURE','decision_ref':'composition-context:'+key,
                     'region_ref':'scope:'+digest(source_range),'source_range':source_range,
                     'cue_token_refs':[e.token_id for e in self.evidence[
                         bisect_left(self.starts,source_range[0]):bisect_left(self.starts,source_range[1])]
                                       if source_range[0]<=e.start and e.end<=source_range[1]],
                     'slot':'COMPOSITION','proof_goals':goals}
            result=self.reader.read(self.state,request)
            if result.get('search_incomplete'):
                from .attention_context import ContextReadError
                raise ContextReadError('COMPOSITION_GOAL_SEARCH_INCOMPLETE')
            # Context may constrain interpretation; it does not license an
            # identity binding or O/C/W truth support on its own.
            keys={'entity_ref','binding_ref','source_tag','premise_support_refs','label',
                  'features','source_context','reference_kind','node_ref'}
            rows=[{k:v for k,v in r.items() if k in keys} for r in result['rows']]
            proofs=[]
            for item in result.get('proof_results',[]):
                # Failed fact lookup says nothing about explicit source syntax.
                # Full results remain in state.context_reads / CONTEXT_READ WAL.
                if item.get('status')!='PROVED':continue
                projected={k:v for k,v in item.items() if k!='proof'}
                if 'proof' in item:
                    proof=item['proof']
                    projected['proof']={'receipt_hash':digest(proof),'conclusion':proof['conclusion'],
                        'premise_support_refs':proof['premise_support_refs'],
                        'rules':[step['request']['rule_id'] for step in proof['derivations']]}
                proofs.append(projected)
            payload={'context':rows,'proofs':proofs} if proofs else rows
            text=json.dumps(payload,ensure_ascii=False,sort_keys=True)
            if len(text)>cfg['context_chars']:
                from .attention_context import ContextReadError
                raise ContextReadError('COMPOSITION_CONTEXT_LIMIT')
            self.context[key]=text if rows or proofs else ''
        text=self.context[key]
        return ('\nAddressed memory context (interpretation only; no implicit identity or factivity): '+text+'\n') if text else ''


@contextmanager
def session(state,release,reader=None):
    token=_current.set(CompositionSession(state,release,reader))
    try:yield _current.get()
    finally:_current.reset(token)


def current(state):
    value=_current.get()
    return value if value is not None and value.state is state else None


def child_key(region,tokens,attachment,infinitive,request):
    def canonical(v):
        if is_dataclass(v):return canonical(asdict(v))
        if isinstance(v,dict):return {k:canonical(x) for k,x in v.items()}
        if isinstance(v,(tuple,list)):return [canonical(x) for x in v]
        if isinstance(v,(set,frozenset)):return sorted(canonical(x) for x in v)
        return v
    return digest(canonical([region.source_range,tokens,attachment,infinitive,request]))
