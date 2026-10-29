"""Reference projection and actual selector boundary; no model-quality claim."""
from types import SimpleNamespace
from ah.formalizer.pipeline import t0
from ah.formalizer.state import TokenEvidence
from ah.formalizer.reference_presentation import label
from ah.formalizer.component_probe import _probe

state=t0('Саша спросил Сашу, придёт ли он.')
state.evidence=[TokenEvidence('Саша','a',0,4),TokenEvidence('Сашу','b',13,17)]
a={'label':'Саша','local_anchor_ref':'a'}
b={'label':'Саша','local_anchor_ref':'b'}
assert label(state,[a])!=label(state,[b])
assert '0:4' in label(state,[a]) and '13:17' in label(state,[b])
# A second grounding path must survive projection; repeated identical evidence
# does not become another referent, and source fragments are not duplicated.
combined=label(state,[a,b,a])
assert combined.count('Current-source occurrence')==2
memory={'label':'Саша; source excerpt: Позвонил из Казани',
        'memory_excerpt':'Позвонил из Казани','memory_excerpt_range':[4,23]}
assert label(state,[memory]).count('Позвонил из Казани')==1
assert label(state,[{'label':'Саша'}])==label(state,[{'label':'Саша'}])
class Selector:
    selection_reply_format='SELECT_LABELS_V1'
    def __init__(self):self.calls=0
    def select(self,prompt):
        self.calls+=1
        assert '0:4' in prompt and '13:17' in prompt
        return '2'
selector=Selector()
release=SimpleNamespace(sha256='release',entries=lambda kind:[{'max_rule_steps':100}])
options=[{'candidate_id':cid,'label':label(state,[row])} for cid,row in [('first',a),('second',b)]]
state.frames=[SimpleNamespace(frame_id='f',predicate_token_ref='a',source_range=(0,len(state.text)),
    argument_token_refs=('a','b'),semantic={'proposed_roles':{'a':'SUBJECT','b':'OBJECT'}})]
state.structural_closed=True
from ah.formalizer.reference_structure import inputs
assert _probe(state,selector,release,'reference','reference',options,state.text,(0,len(state.text)),
              inputs=inputs(state,('b',),options),question='Какое вхождение выбрано?')=='second'
assert selector.calls==1
print('F03 occurrence addressing, all grounding descriptions, excerpt deduplication, wire mapping: PASS')

# Two anchors may share the exact same excerpt window; preserve anchor ranges.
from ah.formalizer.reference_source_context import attach
text='Саша спросил Сашу'
store=SimpleNamespace(
    _journal=SimpleNamespace(scan_unprocessed=lambda *a,**k:[{'payload':{
        'kind':'run_bind','observation_id':'source','version':1,'snapshot_data':{'text':text}}}]),
    ledger=SimpleNamespace(data={'bindings':{'a':{'mention_ref':'tok:0:4'},'b':{'mention_ref':'tok:13:17'}},'supports':{},'nodes':{}}),
    _store=SimpleNamespace(get_element_any_domain=lambda uid:SimpleNamespace(meta={})))
rows=[{'label':'Саша','source_tag':['source',1],'binding_ref':bid,'entity_ref':bid} for bid in ('a','b')]
attach(store,rows)
assert rows[0]['memory_excerpt']==rows[1]['memory_excerpt']
assert rows[0]['memory_anchor_range']!=rows[1]['memory_anchor_range']
assert label(state,[rows[0]])!=label(state,[rows[1]])
print('F03 shared memory excerpt retains distinct source anchors: PASS')

# A qualification outside the old +/-96 window must reach the actual label.
long_text='Саша '+('подробности ' * 25)+'говорил о плане, а не о поездке.'
store._journal.scan_unprocessed=lambda *a,**k:[{'payload':{'kind':'run_bind',
    'observation_id':'source','version':1,'snapshot_data':{'text':long_text}}}]
row={'label':'Саша','source_tag':['source',1],'binding_ref':'a','entity_ref':'a'}
attach(store,[row])
assert 'не о поездке' not in row['memory_excerpt']
assert row['source_context']==long_text and row['source_context_complete']
assert 'не о поездке' in label(state,[row])
print('F03 complete prior source preserves a qualification outside the short excerpt: PASS')
# Event candidates have support paths rather than identity bindings. They
# still need exact source occurrences, even within one identical source text.
rows=[{'label':long_text,'source_tag':['source',1],'binding_ref':'event:'+str(i),
       'entity_ref':'event:'+str(i),'reference_kind':'EVENT','source_ref':ref}
      for i,ref in enumerate(('tok:0:4','tok:5:16'))]
attach(store,rows)
assert all(r['memory_anchor_range'] for r in rows)
assert label(state,[rows[0]])!=label(state,[rows[1]])
print('F03 event references retain source anchors without identity bindings: PASS')
