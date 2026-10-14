"""Program-built unary lexical scope, preserving non-factive adverbs as SOM."""
from .canonical_ledger import digest
from .component_policy import _morph
from .state import FrameCandidate


def wrap(frame, region, token, variant, role, *, entities=(), nominal_role=None):
    # This constructor licenses a scoped reading, not the modifier's factivity.
    # T3 still checks known R-S/R-V/TemplateMap; it may not bypass broken mapping.
    fid = 'component-modifier:'+digest([frame.frame_id, token.token_id, variant.lemma, role, nominal_role, [(e.token_id,_morph(v)) for e,v in entities]])
    frame.semantic['uncovered_token_refs'] = []
    frame.semantic['structural_unresolved'] = False
    frame.semantic['component_questions'] = [q for q in frame.semantic['component_questions']
        if q['kind'] not in {'UNRESOLVED_COMPONENT','RELATION_TO_EVENT'}]
    frame.semantic['component_child'] = fid
    semantic = {'proposed_roles':{e.token_id:nominal_role for e,v in entities},
        'morph_bindings':{token.token_id:_morph(variant), **{e.token_id:_morph(v) for e,v in entities}},
        'lexical_units':{}, 'preposition_bindings':{}, 'missing_required_roles':[],
        'requires_attachment_probe':True, 'uncovered_token_refs':[], 'structural_unresolved':False,
        'relative_temporal':[], 'component_region':region.region_id,
        'proposition_args':{role:{'frame_ref':frame.frame_id, 'attitude':'UNKNOWN'}},
        'component_questions':[{'kind':'MODIFIER_SCOPE','anchor_ref':token.token_id,
            'content_frame_ref':frame.frame_id,'content_asserted':False}]}
    outer = FrameCandidate(fid, 'FLAT', token.span, (token.span, *[e.span for e,v in entities]), tuple(e.span for e,v in entities),
        construction='COMPONENTS_V1', predicate_token_ref=token.token_id,
        argument_token_refs=tuple(e.token_id for e,v in entities), source_range=tuple(region.source_range),
        semantic=semantic, provenance=frame.provenance)
    return [frame, outer]
