"""Projection of established addressed ownership, no word/POS heuristics."""
from pytest import MonkeyPatch
from ah.formalizer.pipeline import t0
from ah.formalizer.nominal_reference_groups import owned_function_refs
from ah.formalizer import nominal_functions
s=t0('шмырлик шмырлик носитель');first,second,head=s.evidence
assert not first.variants and not second.variants
with MonkeyPatch.context() as patch:
    patch.setattr(nominal_functions,'rows',lambda *args:[{
        'function_refs':[first.token_id,head.token_id],'head_ref':head.token_id}])
    assert owned_function_refs(s,s.evidence)=={first.token_id}
    # A head simultaneously carrying the function remains selectable as nominal.
    # Same spelling at another occurrence inherits no ownership constraint.
    assert second.token_id not in owned_function_refs(s,s.evidence)
    assert head.token_id not in owned_function_refs(s,s.evidence)
print('PASS: OOV functional occurrence excluded, identical independent occurrence and shared head retained')
