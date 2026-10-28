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
    def __init__(self,state,release,reader=None,selector=None,morph=None):
        self.state,self.release,self.reader=state,release,reader
        from .composition_tasks import ChildTasks
        from .composition_dispatcher import Dispatcher
        from copy import deepcopy
        rules=release.entries('ProposalPolicy')
        self.dispatcher=Dispatcher(state,rules[0].get('max_rule_steps',20000) if rules else 20000)
        self.tasks=ChildTasks(state,self.dispatcher);self.context={}
        self.selector,self.morph=selector,morph
        self.original={e.token_id:deepcopy(e) for e in state.evidence}
        self.area_inputs=None;self.morphology_scope=None;self.domain_feedback=None
        from .composition_sources import CompositionSources
        self.sources=CompositionSources(state,release)
        self.evidence=sorted(state.evidence,key=lambda e:e.start)
        self.starts=[e.start for e in self.evidence]

    def child(self,key,compute,inputs=None):
        if self.area_inputs:
            region,tokens,_=self.area_inputs
            self.tasks.areas[key]={'source_range':region.source_range,'token_refs':[t.token_id for t in tokens]}
        return self.tasks.child(key,compute,[inputs,self.context_signature()])

    def context_signature(self):
        # Attention ticks are not evidence revisions. The reader freezes the AH
        # memory base and rejects concurrent writes itself.
        return digest([getattr(self.reader,'base',{}).get('memory_hash'),
                       getattr(self.state,'context_facts',())])

    @contextmanager
    def area(self,region,tokens,request):
        previous=self.area_inputs,self.morphology_scope
        self.area_inputs=(region,tokens,request)
        try:yield
        finally:self.area_inputs,self.morphology_scope=previous

    @contextmanager
    def morphology_feedback(self,text):
        previous=self.domain_feedback;self.domain_feedback=text
        try:yield
        finally:self.domain_feedback=previous

    def input_signature(self):
        if not self.area_inputs:return None
        from .composition_dispatcher import canonical
        region,tokens,request=self.area_inputs
        return digest(canonical([region.source_range,[t.token_id for t in tokens],request]))

    def input_question(self,slot=None):
        if not self.area_inputs:return ''
        region,tokens,request=self.area_inputs
        from .composition_tree import InputSlot
        request=request or InputSlot()
        parts=[]
        morphology=slot in {'structural_oov_function','predicate_argument_reading','relative_marker_reading','structural_marker_reading','nominal_external_case'}
        if self.domain_feedback and not morphology:parts.append('Previous local composition: '+self.domain_feedback)
        if request.surrounding_relations and not morphology:
            from .relation_composition import RELATIONS
            parts.append('Already handled outside the target: '+'; '.join(RELATIONS[k] for k in request.surrounding_relations)+
                '. Select another such relation only if the target words themselves express it.')
        if request.output_sort=='EVENT_DESCRIPTION' and not morphology:parts.append('This area must describe an event or state.')
        if not morphology and request.description_context and not request.controller and any(v.pos in {'INFN','PRTS'} for t in tokens for v in t.variants):
            parts.append('This content is not independently asserted. An action description may leave participants unspecified; '
                         'do not invent a performer or copy agreement from an impersonal modal word.')
        if request.independent_subject and not morphology:
            parts.append('No subject is inherited from the surrounding predicate. Determine participants from this content itself; '
                         'do not copy a speaker or an ancestor controller into it.')
        if request.allowed_cases:
            from .probe_wording import reading
            parts.append('The parent requires '+reading({'cases':sorted(request.allowed_cases)})+'.')
        if request.head_ref:
            head=self.original.get(request.head_ref)
            if head:parts.append('The selected head is «'+head.span+'».')
        if request.pending_proposition_roles and not morphology:
            parts.append('A dependent infinitive is supplied separately; its owner is still to be selected. '
                         'Other dependent clauses inside the target still need their own analysis.')
        owned={t.token_id for t in tokens}
        for ref,roles in (request.pending_propositions or {}).items():
            if ref not in owned or morphology:continue
            owner=self.original[ref]
            supplied=[self.original[t].span for t in (request.pending_proposition_sources or {}).get(ref,())
                      if t in self.original]
            parts.append('Only «'+owner.span+'» @'+str(owner.start)+' has separately supplied content ('+
                         ', '.join(sorted(roles))+')'+(' from «'+' '.join(supplied)+'»' if supplied else '')+
                         '. Its source and slot are assigned; its internal analysis is a separate task and is not certified here. Leave that slot open. '
                         'This assigned child is not omitted or referential content to discover again, even though it is outside TARGET. '
                         'Any other parent predicate and dependent clause INSIDE the target must still be connected.')
        if request.agreement_source:
            from .probe_wording import reading
            from .component_policy import _morph as canonical_reading
            governor=request.agreement_source
            parts.append('Agreement governor: «'+governor.span+'»; '+
                ' / '.join(reading(canonical_reading(v)) for v in governor.variants)+'.')
        if request.controller:
            from .control_arguments import members
            from .probe_wording import reading,role
            alias=request.controller
            known=members(alias)
            parts.append('The infinitive subject is the same '+role(alias['role'])+' of the parent: '+
                ('; '.join('«'+self.original[m['token_ref']].span+'» ('+reading(m['morph'])+')' for m in known)
                 if known else 'an omitted participant licensed by agreement')+'.')
        if (request.agreement_source or request.controller) and not morphology:
            parts.append('An absent repeated subject is not a missing event.')
        return ('\nCurrent parent requirements: '+' '.join(parts)+'\n') if parts else ''


    def memory(self,slot,options,source_range,cfg):
        if self.reader is None or len(options)<2:return ''
        # This reader returns the addressed active context, not a different
        # answer per candidate ordering. Reuse it throughout the same area.
        from .context_proofs import compile_goals
        available=self.area_inputs[1] if self.area_inputs else self.evidence[
            bisect_left(self.starts,source_range[0]):bisect_left(self.starts,source_range[1])]
        evidence=[e for e in available if source_range[0]<=e.start and e.end<=source_range[1]]
        try:goals=compile_goals(self.release,evidence,options,cfg['max_candidates'])
        except ValueError as exc:
            from .attention_context import ContextReadError
            raise ContextReadError('COMPOSITION_GOAL_SEARCH_INCOMPLETE') from exc
        key=digest([source_range,goals,self.tasks.feedback,self.input_signature(),self.context_signature()])
        if key not in self.context:
            request={'kind':'STRUCTURE','decision_ref':'composition-context:'+key,
                     'region_ref':'scope:'+digest(source_range),'source_range':source_range,
                     'cue_token_refs':[e.token_id for e in evidence],
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
            from .probe_presentation import readable_memory
            text=readable_memory(rows,proofs)
            if len(text)>cfg['context_chars']:
                from .attention_context import ContextReadError
                raise ContextReadError('COMPOSITION_CONTEXT_LIMIT')
            self.context[key]=text if rows or proofs else ''
        text=self.dispatcher.run('goal:'+key,[key,self.context[key]],lambda:self.context[key],kind='GOAL_CONTEXT',
            source_range=source_range,token_refs=[e.token_id for e in evidence])
        return ('\nAddressed memory context (interpretation only; no implicit identity or factivity): '+text+'\n') if text else ''


@contextmanager
def session(state,release,reader=None,selector=None,morph=None):
    token=_current.set(CompositionSession(state,release,reader,selector,morph))
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
