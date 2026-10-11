"""Source anchors of generated structures, explicitly not semantic coverage."""


def frame_anchors(frames):
    def operator_anchors(tree):
        if not isinstance(tree,dict): return set()
        refs=set(tree.get('anchor_refs',()))
        for child in tree.get('operands',()): refs.update(operator_anchors(child))
        return refs
    refs=set()
    for frame in frames:
        refs.add(frame.get('predicate_token_ref'))
        refs.update(frame.get('argument_token_refs',()))
        semantic=frame.get('semantic',{})
        for unit in semantic.get('lexical_units',{}).values():
            refs.update(unit.get('anchor_refs',()))
        for row in semantic.get('relative_temporal',()):
            refs.update(row.get('anchor_refs',()))
        for row in semantic.get('preposition_bindings',{}).values():
            refs.add(row.get('token_ref'))
        for root in semantic.get('operator_forest',()):
            refs.update(operator_anchors(root))
    return refs-{None}
