"""Scripted K reference through native write; not a live language-model test."""
from pathlib import Path
from tempfile import TemporaryDirectory
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds,Script,Session,ChatBackend,execute_native
import test_structural_relation_tasks as harness


def group():
    return [('nominal_coordination_discovery','Another flat group')]+bounds('nominal_coordination_members','Иван','Иван')+[
        ('nominal_coordination_members_continue','Another piece starts at «Мария»'),
        ('nominal_coordination_members_piece_end','End after «Мария»'),('nominal_coordination_members_continue','0'),
        ('nominal_coordination_marking','This group has explicit')]+bounds('nominal_coordination_markers','и','и')+[
        ('nominal_coordination_markers_continue','0'),('nominal_coordination_discovery','0'),
        ('component_attachment','прийти [conjugated verb]')]


def reference():
    return [('nominal_function','An expression points')]+bounds('nominal_function_source','эти','эти')+[
        ('nominal_function_head','Nominal head «люди»'),
        ('nominal_identity_function','Identify the nominal'),('nominal_function','0')]

for text,first,second,children in [
    ('Иван и Мария пришли и эти люди спят.',('Иван','пришли'),('эти','спят'),relation('LEXICAL')+group()+relation('LEXICAL')+reference()),
    ('эти люди спят и Иван и Мария пришли.',('эти','спят'),('Иван','пришли'),relation('LEXICAL')+reference()+relation('LEXICAL')+group())]:
    steps=relation('AND')+bounds('structural_operand_1',*first)+bounds('structural_operand_2',*second)+[('structural_partition','PARTITION')]+children+[
        ('reference','The whole established group:')]
    with TemporaryDirectory() as tmp,MonkeyPatch.context() as patch:
        sessions=[]
        def capture(*args,**kwargs):
            session=Session(*args,**kwargs);sessions.append(session);return session
        patch.setattr(harness,'Session',capture)
        result,script=run(Path(tmp),patch,text,steps)
        print(text,result['diagnostics'],result['assertions']['ah'])
        assert not result['diagnostics']['codes'],result['diagnostics']
        facts={f['predicate']:f for f in result['assertions']['ah'] if 'predicate' in f}
        assert set(facts)=={'ARRIVE','SLEEP'},facts
        group_value={'group':[{'entity':'ivan'},{'entity':'maria'}]}
        assert facts['ARRIVE']['roles']['AGENT']==group_value,facts
        assert facts['SLEEP']['roles']['AGENT']==group_value,facts
        session=sessions[0]
        from ah.formalizer.nominal_reference_memory import read_active
        group_binding=next(b for b in session.store.ledger.data['bindings'].values() if b.get('binding_kind')=='NOMINAL_GROUP_ANCHOR')
        uid=group_binding['target_ref']
        rows,incomplete=read_active(session.store,session.release,{uid})
        assert not incomplete and rows and all(r['reference_kind']=='GROUP' for r in rows)
        # A second native observation consumes a real frozen active-workspace K.
        session.native_ignition.seed(session.core.ref(uid),1000.0)
        follow='эти люди спят.'
        script2=Script(relation('LEXICAL')+reference()+[('reference','Previously established whole group:')])
        patch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:script2.generate(prompt,**kw))
        payload={'raw_input':{'text':follow,'source_id':'follow-group','revision':1,
            'range':[0,len(follow)],'language':'ru','request_kind':'ASSERTION','batch_kind':'MESSAGE'}}
        second_result=execute_native(session,payload,{'provider':'lmstudio','model':'scripted-source-selection','structure_mode':'region_probes'})
        assert not script2.errors and not script2.steps,(script2.errors,list(script2.steps))
        assert not second_result['diagnostics']['codes'],second_result['diagnostics']
        assert any(b.get('binding_kind')=='NOMINAL_REFERENCE' and b['target_ref']==uid
                   and b.get('context_read_hash') and not b.get('local_group_anchor')
                   for b in session.store.ledger.data['bindings'].values())
        session.native_ignition.seed(session.core.ref(uid),1000.0)
        script3=Script(relation('LEXICAL')+reference()+[('reference','Previously established whole group:')])
        patch.setattr(ChatBackend,'generate',lambda self,prompt,**kw:script3.generate(prompt,**kw))
        query_payload={'raw_input':{**payload['raw_input'],'source_id':'query-group','request_kind':'QUERY'}}
        from ah.formalizer import native_queries as nq
        from ah.agent import InteractionContext
        from copy import deepcopy
        projected=[];original_project=nq.project_native_queries
        def capture_project(*args,**kwargs):
            roots=original_project(*args,**kwargs);projected.extend(roots);return roots
        patch.setattr(nq,'project_native_queries',capture_project)
        supports_before=len(session.store.ledger.data['supports'])
        session.observer_contract='v7-observer-3'
        query_result=execute_native(session,query_payload,{'provider':'lmstudio','model':'scripted-source-selection','structure_mode':'region_probes'})
        assert not script3.errors and not script3.steps,(script3.errors,list(script3.steps))
        assert query_result['query']['status']=='COMPILED',query_result['query']
        assert query_result['query']['formulas']==[{'predicate':'SLEEP','roles':{'AGENT':group_value}}],query_result['query']
        assert query_result['diagnostics']['codes']==['SPEECH_ACT_QUERY'],query_result['diagnostics']
        assert len(session.store.ledger.data['supports'])==supports_before
        bad=deepcopy(projected)
        for root in bad:
            for atom in root.atoms.values():
                for role,value in atom['roles']:
                    if 'member_refs' in value:value['member_refs']=value['member_refs'][:1]
        rejected=nq.compile_native_queries(session.core,bad,InteractionContext())
        assert rejected and all(r.goal is None and 'QUERY_GROUP_MEMBERS_MISMATCH' in r.diagnostics for r in rejected)


print('PASS: earlier/later K source reference, active memory K reference, typed query without assertion, mismatched query members rejected')
