"""Invalid native writes reject at the intended validator and publish no draft."""
import pytest

from ah.core.journal import JournalIntegrityError
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.graph_ops import ensure_function,ensure_link,ensure_node,ensure_template
from ah.formalizer.store_interface import StoreOp
from tools.formalizer_v7_decision_binding import decision_action
from tools.formalizer_v7_extended_binding import Session


@pytest.mark.parametrize('fault,code',[
    ('unknown_g','REGISTRY_REJECT'),('unknown_L','REGISTRY_REJECT'),
    ('open_role_mismatch','OPEN_TEMPLATE_INVALID'),('GOAL_RUN_ROOT','INTEGRITY_ERROR'),
    ('OBSERVATION_OR_DERIVED','INTEGRITY_ERROR'),('missing_support_record','INTEGRITY_ERROR'),
    ('conclusion_target_mismatch','INTEGRITY_ERROR'),
])
def test_invalid_native_draft_rolls_back_preceding_open_template(tmp_path,fault,code):
    s=Session([],tmp_path/'journal.log')
    actual=decision_action(s,'invalid_write_transaction',{'fault':fault,'create_open_t_first':True})
    assert actual['diagnostics']['codes']==[code]
    assert actual['store']['canonical_unchanged'] is True
    assert all(actual['store'][k]==0 for k in ('new_node_count','new_template_count','new_support_count','new_marker_count'))
    assert not s.core.store.has_uid('rollback:T')
    assert not s.core.store.has_uid('rollback:M')


def test_unknown_assertion_retraction_raises_before_durable_mutation(tmp_path):
    s=Session([],tmp_path/'journal.log')
    before=digest(s.store._codec.export(s.core));head=s.store.read_global_head()
    with pytest.raises(JournalIntegrityError,match='INTEGRITY_ERROR: unknown retraction record'):
        s.store.retract('absent-assertion',reason='declared unknown assertion')
    assert digest(s.store._codec.export(s.core))==before
    assert s.store.read_global_head()==head


def test_registered_native_link_checks_registry_and_preserves_identity(tmp_path):
    s=Session([],tmp_path/'journal.log')
    # The independently authored premise gives two existing typed endpoints.
    from tools.formalizer_v7_extended_binding import ATOM,OTHER
    a,_,_=s.obs('left',ATOM);b,_,_=s.obs('right',OTHER)
    payload={'uid':'registered:L','link_type':'IS-A','source_ref':a,'target_ref':b}
    assert ensure_link(s.core,payload)=='registered:L'
    assert ensure_link(s.core,payload)=='registered:L'
    with pytest.raises(ValueError,match='INTEGRITY_ERROR: link content changed'):
        ensure_link(s.core,{**payload,'target_ref':a})
    assert len([link for link in s.core.store.links() if link.uid=='registered:L'])==1


def test_unknown_and_repeated_assertion_retraction_export_actual_api_result(tmp_path):
    s=Session([],tmp_path/'journal.log')
    unknown=s.action('explicit_assertion_retraction',{'mode':'UNKNOWN_ID','assertion_id':'A'})
    assert unknown['diagnostics']['codes']==['INTEGRITY_ERROR']
    assert unknown['journal']['time_retraction_count']==0
    repeated=s.action('explicit_assertion_retraction',{'mode':'REPEAT_ID','assertion_id':'A'})
    assert repeated['diagnostics']['codes']==[]
    assert repeated['journal']['time_retraction_count']==1
    assert repeated['store']['support_alive'] is True
