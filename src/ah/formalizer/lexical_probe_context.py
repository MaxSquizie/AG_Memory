"""T4 views of already selected structure; no new decomposition or binding."""
from .composition_tree import slots,leaves
from .component_source import frame_view
from .probe_wording import role


def build(state,frame):
    by_id={f.frame_id:f for f in state.frames}
    evidence={e.token_id:e for e in state.evidence}
    lines=[];seen=set()
    def describe(owner):
        if owner.frame_id in seen:return
        seen.add(owner.frame_id)
        for tid,r in owner.semantic.get('proposed_roles',{}).items():
            e=evidence[tid]
            lines.append('«'+owner.anchor_span+'»: '+role(r)+' = «'+e.span+'» @'+str(e.start))
        for slot in slots(owner):
            children=[by_id[r] for r in sorted(leaves(slot.tree)) if r in by_id]
            content=' / '.join(frame_view(state,c).strip() for c in children)
            lines.append('«'+owner.anchor_span+'»: '+role(slot.name)+' content = «'+content+'»; scope='+slot.metadata.get('attitude','not independently asserted'))
            for child in children:describe(child)
    describe(frame)
    # Preserve the original enclosing utterance: child inventories alone lose
    # connecting words, quotation perspective and operator scope.
    lo,hi=frame.source_range
    try:
        area=state.region_forest.container(lo,hi,kinds={'SENTENCE'})
        lo,hi=area.source_range
    except (ValueError,AttributeError):pass
    context='TARGET: '+frame_view(state,frame).strip()+'\nCONTEXT (evidence only): '+state.text[lo:hi]
    established=('ESTABLISHED STRUCTURE (do not reassign): '+'; '.join(lines)+'. ') if lines else ''
    return context,established
