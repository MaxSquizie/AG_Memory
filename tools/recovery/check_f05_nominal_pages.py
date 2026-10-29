"""Real probe codecs across pages; scripted answers, no language-model claim."""
from types import SimpleNamespace as NS
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.reference_structure import inputs
from ah.formalizer.nominal_reference_pages import select,live


def run(replies, count=65, targets=None, maximum=8192, width=20, budget=1000):
    state=t0('этот человек спит')
    state.budget.llm_limit=budget
    t=state.evidence[1]
    state.structural_closed=True
    state.frames=[FrameCandidate('frame','FLAT',state.text,(),predicate_token_ref=t.token_id,
        argument_token_refs=(t.token_id,),source_range=(0,len(state.text)),semantic={})]
    options=[{'candidate_id':str(i),'label':'Source person '+str(i)+' '+(str(i)*width)} for i in range(count)]
    targetmap={str(i):str(i) for i in range(count)} if targets is None else targets
    calls=[];answers=iter(replies)
    def answer(prompt):
        calls.append(prompt)
        return next(answers)
    selector=NS(selection_reply_format='SELECT_LABELS_V1',select=answer,limits=NS(max_prompt_chars=maximum))
    result,proofs,incomplete=select(state,NS(sha256='release',entries=lambda kind:[{'max_rule_steps':100}]),
        selector,'reference-task',options,state.text,(0,len(state.text)),targetmap,
        lambda page:inputs(state,(t.token_id,),page),'Identify this person using the supplied evidence.')
    return state,result,proofs,incomplete,calls

# All pages must be inspected, including after a positive response.
s,c,p,inc,calls=run(['0','0','1'])
assert c=='64' and not inc and len(calls)==3 and live(s,p)
assert not s.decisions['reference-task'].search_complete
assert all(s.text in x for x in calls)
s,c,p,inc,calls=run(['1','0','1'])
assert c is None and not inc and s.decisions['reference-task'].outcome=='AMBIGUOUS'
s,c,p,inc,calls=run(['1','?','0'])
assert c is None and inc and len(calls)==3
s,c,p,inc,calls=run(['0','0','0'])
assert c is None and not inc and s.decisions['reference-task'].outcome=='NO_CANDIDATE'
s,c,p,inc,calls=run(['1,2','0','0'])
assert c is None and not inc and len(s.decisions['reference-task'].selected)==2
s,c,p,inc,calls=run(['1','0','1'],targets={str(i):'same' for i in range(65)})
assert c=='0' and not inc and live(s,p)
s.component_probe_records[p[1]['decision_ref']]['superseded_by']='revision'
assert not live(s,p), 'retired negative page cannot license unique identity'
# Oversized pages subdivide without cutting context or retaining a terminal limit.
s,c,p,inc,calls=run(['0']*16,count=8,maximum=4000,width=450)
assert c is None and not inc and len(calls)>1
assert not s.diagnostics,[(d.code,d.detail) for d in s.diagnostics]
# A positive page followed by budget exhaustion is not a complete choice.
s,c,p,inc,calls=run(['1','0'],budget=2)
assert c is None and inc and len(calls)==2
# Even one full candidate/context that cannot fit remains explicitly incomplete.
s,c,p,inc,calls=run([],count=1,maximum=100,width=450)
assert c is None and inc and not calls
print('PASS: late candidate, competing pages, unknown, all-negative, multiple, equivalent target, retired negative proof, prompt splitting, irreducible limit')
