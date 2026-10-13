"""TEST_ONLY registered membership relation, independent of diary vocabulary."""
from ah.model.types import ActantRole,Domain


def extend(manifest,core):
    if core is None:raise ValueError('narrative fixture requires actual AH core')
    resources={r['kind']:r['entries'] for r in manifest['entries']}
    sid='GROUP_HAS_MEMBER';symbol='fixture:S:'+sid;tid='fixture:T:'+sid
    if not core.store.has_uid(symbol):core.add_abstract_symbol({'group has member'},uid=symbol)
    if not core.store.has_uid(tid):core.add_template(Domain.C,core.ref(symbol),(ActantRole.SUBJECT,ActantRole.OBJECT),uid=tid)
    resources['R-S'].append({'sense_id':sid,'lemma':'членство','POS':'NOUN'})
    resources['TemplateMap'].append({'sense_id':sid,'template_ref':tid,'roles':['SUBJECT','OBJECT']})
    resources['R-V'].append({'sense_id':sid,'state_class':'STATE','roles':[
        {'role_id':role,'argument_types':['ENTITY'],'cardinality':{'min':1,'max':1},'allowed_cases':[],'optionality':False}
        for role in ('SUBJECT','OBJECT')]})
    resources['ProposalPolicy'][0]['composition']['narrative_groups']={'version':'OPEN_NARRATIVE_GROUP_V1','sense_id':sid,'template_ref':tid}


def install_recovered(store):
    """Explicit development resource installation after restoring older AH."""
    with store._journal.atomic(),store._store._lock:
        store._refresh()
        if store.has_uid('fixture:T:GROUP_HAS_MEMBER'):return
        draft=store._draft()
        draft.add_abstract_symbol({'group has member'},uid='fixture:S:GROUP_HAS_MEMBER')
        draft.add_template(Domain.C,draft.ref('fixture:S:GROUP_HAS_MEMBER'),(ActantRole.SUBJECT,ActantRole.OBJECT),uid='fixture:T:GROUP_HAS_MEMBER')
        store._write_unit(draft,tx_ref='TEST_ONLY:install-narrative-membership-v1',extra={'kind':'TEST_ONLY_RESOURCE_INSTALL'})
