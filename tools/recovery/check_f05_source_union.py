"""Union boundary contracts with controlled producers, no model evidence."""
from types import SimpleNamespace
from pytest import MonkeyPatch
from ah.formalizer.pipeline import t0
from ah.formalizer.state import FrameCandidate
from ah.formalizer.composition_source_union import merge
from ah.formalizer import component_constraints,composition_equivalence,partial_composition,composition_children

region=SimpleNamespace(region_id='area',source_range=(0,6))
tokens=[SimpleNamespace(token_id='word')]
def frame(name):return FrameCandidate(name,'FLAT','source',(),semantic={})
with MonkeyPatch.context() as patch:
    patch.setattr(component_constraints,'accepts_bundle',lambda s,r,t,b:all(f.frame_id!='conflict' for f in b))
    patch.setattr(composition_equivalence,'coalesce',lambda s,rel,r,b:(b,set()))
    patch.setattr(composition_equivalence,'describe',lambda s,r,b:r.frame_id)
    patch.setattr(partial_composition,'close_alternatives',lambda *a:False)
    def pending(s,*args):s.diag('COMPONENT_PROBE_FAILED','union selection')
    patch.setattr(composition_children,'select_child',pending)
    for grammar in [False,True]:
        for code in ['COMPUTATION_LIMIT','COMPONENT_SEARCH_INCOMPLETE','PROVIDER_UNAVAILABLE','RESOURCE_MISSING','INTEGRITY_ERROR','COMPONENT_PROBE_FAILED']:
            s=t0('source');s.diag(code,'producer');old=s.diagnostics[0]
            result=merge(s,None,None,region,tokens,{},[frame('grammar')] if grammar else [],[frame('component')],0)
            assert all(f.semantic.get('structural_unresolved') for f in result),(grammar,code)
            assert any(d is old for d in s.diagnostics)
    # No-grammar route must enforce the same established occurrence constraints.
    s=t0('source');result=merge(s,None,None,region,tokens,{},[],[frame('conflict')],0)
    assert result[0].semantic['structural_rejection']=='ESTABLISHED_SOURCE_CONSTRAINT_CONFLICT'
    # A diagnostic from another child cannot be erased by a surviving root.
    s=t0('source');s.diag('CHILD_NEEDS_CONTEXT','other child');old=s.diagnostics[0]
    result=merge(s,None,None,region,tokens,{},[],[frame('component')],0)
    assert any(d is old for d in s.diagnostics)
    assert not result[0].semantic.get('structural_unresolved')
    s=t0('source');s.diag('CHILD_NEEDS_CONTEXT','other child');old=s.diagnostics[0]
    result=merge(s,None,None,region,tokens,{},[frame('grammar')],[],0)
    assert any(d is old for d in s.diagnostics)
    assert not result[0].semantic.get('structural_unresolved')
    # A failure produced during union selection survives, too.
    s=t0('source');result=merge(s,None,None,region,tokens,{},[frame('grammar')],[frame('component')],0)
    assert any(d.code=='COMPONENT_PROBE_FAILED' for d in s.diagnostics)
    assert all(f.semantic['structural_unresolved'] for f in result)
print('PASS: both union routes preserve resource/budget failure, source constraints, child diagnostics and selection failure')
