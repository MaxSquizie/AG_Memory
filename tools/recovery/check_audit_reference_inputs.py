"""Real reference consumer/codec with scripted answers; no live-model claim."""
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence, FrameCandidate
from ah.formalizer.coreference import resolve_references
from ah.formalizer.reference_structure import inputs, describe
from ah.formalizer.component_probe import _probe

release=SimpleNamespace(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self,answer='1'):self.answer=answer;self.prompts=[]
    def select(self,prompt):self.prompts.append(str(prompt));return self.answer

def fixture():
    s=t0('Саша сказал Саше что он не придёт')
    s.evidence=[TokenEvidence(text,tid,lo,hi) for text,tid,lo,hi in [
        ('Саша','a',0,4),('сказал','say',5,11),('Саше','b',12,16),('он','he',21,23),('придёт','come',27,33)]]
    s.frames=[FrameCandidate('outer','FLAT','сказал',(),predicate_token_ref='say',
        argument_token_refs=('a','b'),source_range=(0,len(s.text)),semantic={
            'proposed_roles':{'a':'SUBJECT','b':'RECIPIENT'},'proposition_args':{'CONTENT':{
                'tree':{'operator':'NOT','operands':[{'frame_ref':'inner'}]},'attitude':'REPORTED'}},
            'discourse_scope':{'speech_act':'ASSERTION'}}),
        FrameCandidate('inner','FLAT','придёт',(),predicate_token_ref='come',
            argument_token_refs=('he',),source_range=(21,len(s.text)),semantic={
                'proposed_roles':{'he':'SUBJECT'},'component_child':'outer',
                'discourse_scope':{'speech_act':'CONTENT','parent_refs':['outer']}})]
    s.structural_closed=True
    rows={uid:[{'entity_ref':uid,'binding_ref':'local:'+tid,'local_anchor_ref':tid,
                'label':'Саша','premise_support_refs':[]}] for uid,tid in [('first','a'),('second','b')]}
    return s,rows

for answer,expected in [('1','first'),('0',None),('?',None),('1,2',None)]:
    s,rows=fixture();sel=Selector(answer)
    resolve_references(s,{'he':rows},sel,release)
    assert s.observation['entity_bindings'].get('he')==expected
    prompt=sel.prompts[0]
    assert 'recipient or addressee' in prompt and '12:16' in prompt
    assert 'negation of' in prompt and 'nested content (REPORTED)' in prompt
    assert 'Several numbers mean alternative referents' in prompt
    assert s.text in prompt

s,rows=fixture();sel=Selector()
options=[{'candidate_id':'one','label':'first referent'}]
task=inputs(s,('he',),options)
assert not task.errors(s,'reference',options,(21,23))
assert _probe(s,sel,release,'p','reference',options,s.text,(21,23),inputs=task)=='one'
assert _probe(s,sel,release,'p','reference',options,s.text,(21,23),inputs=task)=='one'
assert len(sel.prompts)==1
# Same IDs/text with revised roles must not replay an answer to the old task.
s.frames[0].semantic['proposed_roles']={'a':'RECIPIENT','b':'SUBJECT'}
assert _probe(s,sel,release,'p','reference',options,s.text,(21,23),inputs=task) is None
assert len(sel.prompts)==1
assert _probe(s,sel,release,'p','reference',options,s.text,(21,23),inputs=inputs(s,('he',),options))=='one'
assert len(sel.prompts)==2
# Missing declaration cannot be bypassed by clarification or a cached answer.
s.observation['clarification_choices']={'p':'one'}
assert _probe(s,sel,release,'p','reference',options,s.text,(21,23)) is None
assert len(sel.prompts)==2
s,rows=fixture();sel=Selector();s.structural_closed=False
assert _probe(s,sel,release,'p','reference',options,s.text,(21,23),inputs=inputs(s,('he',),options)) is None
assert not sel.prompts
# Explicit partiality elsewhere must not make current roles into alleged facts.
s,rows=fixture();s.frames.append(FrameCandidate('unfinished','FLAT','Саша',(),
    predicate_token_ref='a',semantic={'structural_unresolved':True}))
assert 'structure unresolved' in describe(s)[0]
assert not inputs(s,('he',),options).errors(s,'reference',options,(21,23))
print('F03/F04 reference roles/scope, actual consumer outcomes, replay revision, missing/stale inputs: PASS')

# A time scope on the enclosing negation is not a time scope on its leaf.
s,_=fixture()
node=s.frames[0].semantic['proposition_args']['CONTENT']['tree']
node['region']={'kind':'EXISTENTIAL','lo':None,'hi':None,'expressions':[{'raw':'завтра'}]}
text,errors=describe(s)
assert not errors and 'time constraint on this WHOLE expression' in text and '«завтра»' in text
assert text.index('time constraint on this WHOLE expression')<text.index('negation of')
# Unsupported scopes must remain visible and prevent an incomplete question.
node['operator']='UNSUPPORTED_SCOPE'
task=inputs(s,('he',),options)
assert 'SCOPE_VIEW_UNSUPPORTED' in task.errors(s,'reference',options,(21,23))
print('F03/F04 temporal scope retained; unsupported scope explicitly blocks: PASS')
s,_=fixture()
s.frames[0].semantic['nominal_args']=[{'host_token_ref':'b','host_role':'SUBJECT','frame_ref':'inner'}]
s.frames[0].semantic['proposition_args']={}
text,errors=describe(s)
assert not errors and 'nominal description of «Саше» at characters 12:16' in text
assert '0 nested content' not in text
print('F03 nominal description retains its exact host occurrence: PASS')
