"""Declared minimal-scope assumption; never a source-grounded resolution."""
from copy import deepcopy
from .canonical_ledger import digest


POLICY = 'ASK_THEN_MINIMAL_MEMBER_SET_V1'


def least(options):
    if (not isinstance(options,list) or len(options)<2 or
        any(not isinstance(o,dict) or not isinstance(o.get('candidate_id'),str) or
            not isinstance(o.get('member_refs'),list) or not o['member_refs'] or
            any(not isinstance(t,str) or not t for t in o['member_refs']) for o in options) or
        len({o['candidate_id'] for o in options})!=len(options)):
        return None
    members={o['candidate_id']:set(o['member_refs']) for o in options}
    minima=[k for k,s in members.items() if s and all(s < other for j,other in members.items() if j!=k)]
    return minima[0] if len(minima)==1 and len(members)>1 else None


def select(state, release, key, choices, member_sets, cfg):
    if cfg.get('refinement',{}).get('ambiguity_policy')!=POLICY:return None
    decision=state.decisions.get(key)
    # No policy rescue of budget, transport, malformed reply or NONE_FIT.
    if decision is None or decision.selector_outcome not in {'INSUFFICIENT_CONTEXT','MULTIPLE_ADMISSIBLE'}:return None
    eligible=set(decision.candidates)
    if decision.selector_outcome=='MULTIPLE_ADMISSIBLE':
        rows=[r for r in decision.history if r.get('kind')=='CLOSED_PROBE_ALTERNATIVES']
        if not rows:return None
        eligible=set(rows[-1]['selected'])
    options=[{**deepcopy(o),'member_refs':sorted(member_sets[o['candidate_id']])} for o in choices if o['candidate_id'] in eligible]
    for offer in state.clarification_candidates:
        if offer['decision_ref']==key:
            offer['options']=deepcopy(options)
    delivery=state.observation.get('clarification_delivery',{}).get(key,
        state.observation.get('clarification_channel','AVAILABLE'))
    selected=least(options)
    if delivery not in {'UNAVAILABLE','IGNORED'} or selected is None:return None
    body={'policy':POLICY,'decision_ref':key,'source_tag':[state.source_uid,state.interpretation_version],
          'resource_sha256':release.sha256,'options':options,'selected':selected,
          'reason':delivery,'status':'ASSUMED_UNRESOLVED'}
    row={'uncertainty_id':'uncertainty:'+digest(body),**body}
    state.syntax_trace.append({'kind':'REFINEMENT_SCOPE_ASSUMPTION',**deepcopy(row)})
    state.diag('REFINEMENT_SCOPE_ASSUMED',key)
    return row


def validate(link):
    row=link.get('scope_assumption')
    if row is None:return
    body={k:v for k,v in row.items() if k!='uncertainty_id'}
    if (link.get('kind')!='NOMINAL' or row.get('policy')!=POLICY or
        row.get('status')!='ASSUMED_UNRESOLVED' or row.get('reason') not in {'UNAVAILABLE','IGNORED'} or
        row.get('source_tag')!=link.get('source_tag') or not row.get('decision_ref') or
        not row.get('resource_sha256') or not isinstance(row.get('options'),list) or
        not isinstance(row.get('selected'),str) or not row['selected'] or
        row.get('selected')!=least(row['options']) or
        row.get('uncertainty_id')!='uncertainty:'+digest(body)):
        raise ValueError('REFINEMENT_SCOPE_ASSUMPTION_INVALID')
