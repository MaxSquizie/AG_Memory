"""One typed view of existing frame/operand IR; no parallel graph or AH writes.

All composition clients use slots and references, never frame-id prefixes.
Wire dictionaries remain the sealed, journalled representation.
"""
from dataclasses import dataclass
from .canonical_ledger import digest


def reference(frame):
    return {'frame_ref': frame.frame_id if hasattr(frame, 'frame_id') else frame}


def associative_node(operator, operands, anchors=()):
    """Remove administrative bracketing only across bare associative nodes.

    Temporal or other semantic annotations are scope boundaries and survive.
    Source order remains available for ordinary contiguous scope candidates.
    """
    from .operator_algebra import OPERATORS
    spec=OPERATORS.get(operator)
    children=[]; refs=list(anchors)
    for child in operands:
        if (spec and spec.associative and child.get('operator')==operator
                and set(child)<={'operator','operands','anchor_refs'}):
            children.extend(child['operands']);refs.extend(child.get('anchor_refs',()))
        else:
            children.append(child)
    return {'operator':operator,'operands':children,'anchor_refs':list(dict.fromkeys(refs))}


def content(argument):
    if 'tree' in argument:
        return argument['tree']
    if 'frame_ref' in argument:
        return reference(argument['frame_ref'])
    raise ValueError('COMPOSITION_SLOT_UNCLOSED')


def leaves(tree):
    """Direct lexical leaves of an expression, excluding typed literal slots."""
    result = set()
    pending = [tree]
    while pending:
        node = pending.pop()
        if 'frame_ref' in node:
            result.add(node['frame_ref'])
        else:
            pending.extend(node.get('operands', ()))
    return result


@dataclass(frozen=True)
class ChildSlot:
    owner: str
    name: str
    kind: str
    tree: dict
    metadata: dict


@dataclass(frozen=True)
class InputSlot:
    """Constraints passed down to a child, independent of ancestor depth."""
    output_sort: str = 'PROPOSITION'
    head_ref: str | None = None
    allowed_cases: frozenset = frozenset()
    inside_attitude: bool = False
    proposition_slots: dict | None = None
    agreement_source: object = None
    pending_proposition_roles: frozenset = frozenset()
    controller: object = None
    constraint_signature: str = ''
    surrounding_relations: tuple = ()


def slots(frame):
    for role, arg in frame.semantic.get('proposition_args', {}).items():
        yield ChildSlot(frame.frame_id, role, 'PROPOSITION', content(arg), arg)
    for index, arg in enumerate(frame.semantic.get('nominal_args', ())):
        yield ChildSlot(frame.frame_id, str(index), 'NOMINAL', content(arg), arg)


def expression(frame):
    return frame.semantic.get('component_scope_tree') or reference(frame)


def forests(frames, logical_roots=()):
    found = {}
    def add(tree):
        found.setdefault(digest(tree), tree)
    for tree in logical_roots:
        add(tree)
    for frame in frames:
        sem = frame.semantic
        if sem.get('component_scope_tree') and not sem.get('component_child') and not sem.get('coordination_owner') and not sem.get('structural_unresolved'):
            add(sem['component_scope_tree'])
        for tree in sem.get('operator_forest', ()):
            add(tree)
    return list(found.values())


def embedded(frames, trees=()):
    found = set()
    for tree in trees:
        found.update(leaves(tree))
    for frame in frames:
        for slot in slots(frame):
            found.update(leaves(slot.tree))
    return found


def roots(frames):
    """Return candidates at the composition boundary, preserving scope carriers."""
    candidates = [f for f in frames if not f.semantic.get('structural_unresolved')]
    children = embedded(frames)
    return [f for f in candidates if f.frame_id not in children and not f.semantic.get('component_child')
            and f.semantic.get('composition_group_root',f.frame_id)==f.frame_id]


def internalize(frames, child=None, parent=None):
    """Consume a boundary expression as structure, retaining its audit forest.

    A child's operator forest must never become a second assertion root merely
    because its parent uses a proposition slot, nominal slot or unary operator.
    The parent carries the expression explicitly through its typed slot/tree.
    """
    if child is not None:
        if parent is None:raise ValueError('COMPOSITION_PARENT_REQUIRED')
        child.semantic['component_child']=parent.frame_id
    for frame in frames:
        if frame.semantic.get('operator_forest'):
            frame.semantic['nested_operator_forest']=frame.semantic.pop('operator_forest')


def unary_modifier(frame):
    """A lexical modifier is a declared slot relation, not an ID convention."""
    children = list(slots(frame))
    if len(children) != 1 or children[0].kind != 'PROPOSITION':
        return None
    if not any(q.get('kind') == 'MODIFIER_SCOPE' for q in frame.semantic.get('component_questions', ())):
        return None
    return children[0]


def validate(frames, trees=()):
    """Validate closure/cycles once on the DAG; shared children are legal."""
    from .scope_boundaries import validate as validate_boundaries
    validate_boundaries(frames)
    by_id = {f.frame_id: f for f in frames}
    if len(by_id) != len(frames):
        raise ValueError('COMPOSITION_DUPLICATE_FRAME')
    edges = {fid: set().union(*(leaves(s.tree) for s in slots(f))) for fid, f in by_id.items()}
    for fid, f in by_id.items():
        if f.semantic.get('pending_proposition_roles'):
            raise ValueError('COMPOSITION_SLOT_UNCLOSED')
        # A scope carrier stores an enclosing expression, not an outgoing
        # content edge from this lexical node to every sibling in that scope.
    referenced = set().union(*(leaves(t) for t in trees),
                             *(leaves(expression(f)) for f in frames), *edges.values())
    if referenced - by_id.keys():
        raise ValueError('COMPOSITION_SLOT_UNCLOSED')
    done, active = set(), set()
    for start in by_id:
        stack = [(start, False)]
        while stack:
            node, leaving = stack.pop()
            if leaving:
                active.remove(node); done.add(node)
            elif node not in done:
                if node in active:
                    raise ValueError('COMPOSITION_CYCLE')
                active.add(node)
                stack.append((node, True))
                stack.extend((child, False) for child in sorted(edges[node], reverse=True))


def finalize(state, region, frames):
    """One closure check at the outer boundary, before any structural seal.

    Internal composers may carry reserved slots. A finalized component cannot.
    Rejected alternatives remain addressable and are not checked as facts.
    """
    selected=[f for f in frames if not f.semantic.get('structural_unresolved')]
    if not selected:
        state.syntax_trace.append({'kind':'COMPOSITION_PENDING' if frames else 'COMPOSITION_EMPTY',
                                   'region_ref':region.region_id,'frame_refs':[f.frame_id for f in frames]})
        return
    try:
        validate(selected, forests(selected))
        from .morphology_domain import validate_uses
        validate_uses(state,selected)
    except ValueError as exc:
        code=str(exc)
        state.diag(code,region.region_id)
        for frame in selected:
            frame.semantic['structural_unresolved']=True
            frame.semantic['structural_rejection']=code
        state.syntax_trace.append({'kind':'COMPOSITION_REJECTED','region_ref':region.region_id,
                                   'reason':code,'frame_refs':[f.frame_id for f in selected]})
        return
    state.syntax_trace.append({'kind':'COMPOSITION_CLOSED','region_ref':region.region_id,
                               'frame_refs':[f.frame_id for f in selected]})
