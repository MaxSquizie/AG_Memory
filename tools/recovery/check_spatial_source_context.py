"""Frozen active-place reader must retain source evidence beyond its excerpt."""
from types import SimpleNamespace
from ah.formalizer.spatial_memory import read_active
text='Здесь '+('длинное описание '*30)+'это место относится к первому рассказу'
place={'source_tag':['old',1],'source_range':[0,5],'raw':'Здесь','location_kind':'LOCATION'}
binding={'binding_kind':'SPATIAL_ANCHOR','target_ref':'place','source_tag':['old',1]}
ledger=SimpleNamespace(data={'bindings':{'b':binding}},paths=lambda:(),binding_live=lambda *args:True)
journal=SimpleNamespace(scan_unprocessed=lambda:[{'payload':{'kind':'run_bind','observation_id':'old',
    'version':1,'snapshot_data':{'text':text}}}])
store=SimpleNamespace(ledger=ledger,_journal=journal,
    _store=SimpleNamespace(get_element_any_domain=lambda uid:SimpleNamespace(meta={'relative_place':place})))
release=SimpleNamespace(entries=lambda kind:[{'spatial_references':{'max_candidates':8}}])
rows,incomplete=read_active(store,release,{'place'})
assert not incomplete and len(rows)==1 and rows[0]['source_context']==text
assert 'первому рассказу' not in rows[0]['memory_excerpt']
assert rows[0]['source_range']==[0,5] and rows[0]['source_context_available']
text='несовпадающий источник'
rows,incomplete=read_active(store,release,{'place'})
assert not rows[0]['source_context_available'] and rows[0]['source_context']==''
print('Spatial active read: exact anchor kept, full distant context retained, source mismatch explicit: PASS')
