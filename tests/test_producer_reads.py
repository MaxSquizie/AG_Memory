"""Capture successful closures, never intermediate attempts or DFS order."""
from ah.formalizer.pipeline import t0
from ah.formalizer.composition_dispatcher import Dispatcher
from ah.formalizer.producer_reads import capture


def test_cached_probe_read_is_captured_and_frozen(monkeypatch):
    from ah.formalizer import dispatch_evidence
    stamps={'a':'old'}
    monkeypatch.setattr(dispatch_evidence,'probe_stamp',lambda s,k:stamps[k])
    d=Dispatcher(t0('source'))
    d.run('probe:a',None,lambda:1,kind='PROBE')
    with capture(d) as reads:
        assert d.run('probe:a',None,lambda:0,kind='PROBE')==1
        stamps['a']='new'
        # Mutation after consumption cannot rewrite the captured stamp.
        d.nodes['probe:a']['probe_stamp']='new'
    assert reads.snapshot()['probes']=={'a':'old'}


def test_addressed_discard_removes_replaced_not_independent_reads(monkeypatch):
    from ah.formalizer import dispatch_evidence
    monkeypatch.setattr(dispatch_evidence,'probe_stamp',lambda s,k:k)
    d=Dispatcher(t0('source'))
    with capture(d) as reads:
        for key in ('old','other'):
            d.run('probe:'+key,None,lambda:1,kind='PROBE')
        d.discard_reads(['probe:old'],'REPAIRED_OWNER')
        d.run('probe:new',None,lambda:1,kind='PROBE')
    assert set(reads.snapshot()['probes'])=={'other','new'}


def test_abandoned_dispatch_attempt_does_not_enter_source_capture(monkeypatch):
    from ah.formalizer import dispatch_evidence
    monkeypatch.setattr(dispatch_evidence,'probe_stamp',lambda s,k:k)
    d=Dispatcher(t0('source'))
    def parent():
        d.run('probe:old',None,lambda:1,kind='PROBE')
        d.discard_attempt()
        return d.run('probe:new',None,lambda:2,kind='PROBE')
    with capture(d) as reads:
        assert d.run('parent',None,parent,kind='COMPOSITION')==2
    assert set(reads.snapshot()['probes'])=={'new'}


def test_cached_constraint_does_not_overwrite_later_direct_read(monkeypatch):
    from ah.formalizer import dispatch_evidence
    monkeypatch.setattr(dispatch_evidence,'valid',lambda *a:True)
    d=Dispatcher(t0('source'))
    old={'region_ref':'r','task_scope':'s','signature':'old'}
    new={**old,'signature':'new'}
    def compute():
        d.observe('CONSTRAINT_SET',old)
        return 1
    d.run('cached',None,compute,kind='COMPOSITION')
    with capture(d) as reads:
        d.observe('CONSTRAINT_SET',new)
        d.run('cached',None,compute,kind='COMPOSITION')
    assert {r['value']['signature'] for r in reads.snapshot()['external']}=={'old','new'}


def test_nested_discard_prunes_named_dependency_preserving_other_branch(monkeypatch):
    from ah.formalizer import dispatch_evidence
    monkeypatch.setattr(dispatch_evidence,'probe_stamp',lambda s,k:k)
    d=Dispatcher(t0('source'))
    def outer():
        return tuple(d.run('probe:'+key,None,lambda:1,kind='PROBE') for key in ('old','other'))
    with capture(d) as reads:
        d.run('outer',None,outer,kind='COMPOSITION')
        d.discard_reads(['probe:old'],'REPAIRED_OWNER')
        d.run('probe:new',None,lambda:2,kind='PROBE')
    assert set(reads.snapshot()['probes'])=={'other','new'}


def test_cached_goal_keeps_context_obligation():
    d=Dispatcher(t0('source'))
    def outer():return d.run('goal:memory',None,lambda:'context',kind='GOAL_CONTEXT')
    d.run('outer',None,outer,kind='COMPOSITION')
    with capture(d) as reads:d.run('outer',None,outer,kind='COMPOSITION')
    assert reads.snapshot()['contexts']==['goal:memory']
