"""A malformed wire may be corrected once; semantic abstention is final."""
from types import SimpleNamespace
from ah.formalizer.selection_exchange import exchange
from ah.formalizer.selection_protocol import DecisionSchema,Relation,ProtocolError
from ah.formalizer.selection_labels import PROTOCOL_VERSION,build_label_selection_prompt
from ah.formalizer.provider_adapter import BudgetExceeded
from ah.formalizer.state import Decision

ids=('left','right')
schema=DecisionSchema('fixture',{x:Relation(x,x,0,(),x) for x in ids})
prompt=build_label_selection_prompt(slot_id='choice',frame_id='f',context_span='source',
    mentions={},schema=schema,candidates=ids)

def run(replies,limit=2,maximum=8192):
    calls=[];budget=SimpleNamespace(used=0)
    def spend():
        if budget.used>=limit:raise BudgetExceeded('COMPUTATION_LIMIT')
        budget.used+=1
    budget.spend_llm=spend
    answers=iter(replies)
    selector=SimpleNamespace(selection_reply_format=PROTOCOL_VERSION,
        select=lambda p:(calls.append(p),next(answers))[1])
    d=Decision('choice','f',ids)
    try:result=exchange(SimpleNamespace(budget=budget),selector,d,prompt,schema,ids,maximum)
    except (ProtocolError,BudgetExceeded) as error:result=error
    return result,d,calls,budget

for raw,outcome in [('0','NONE_FIT'),('?','INSUFFICIENT_CONTEXT'),('1,2','MULTIPLE_ADMISSIBLE')]:
    r,d,c,b=run([raw]);assert r.outcome==outcome and len(c)==1
r,d,c,b=run(['98','2'])
assert r.selected==('right',) and b.used==2 and len(c)==2
assert str(prompt) in c[1] and '"98"' in c[1]
assert c[0].selection_audit==c[1].selection_audit
assert d.history[-1]['kind']=='SELECTION_PROTOCOL_REPAIRED'
assert any(h.get('raw_response')=='98' for h in d.history)
r,d,c,b=run(['98','?']);assert r.outcome=='INSUFFICIENT_CONTEXT' and len(c)==2
r,d,c,b=run(['98','98','1']);assert isinstance(r,ProtocolError) and len(c)==2
r,d,c,b=run(['98','1'],limit=1);assert isinstance(r,BudgetExceeded) and len(c)==1
r,d,c,b=run(['98','1'],maximum=len(prompt));assert isinstance(r,BudgetExceeded) and len(c)==1
print('PASS: strict format repair, immutable choice map, raw audit, bounded attempts and budgets; no retry for 0/?/multiple')
