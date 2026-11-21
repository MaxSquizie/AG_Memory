from ah.model import ActantRole, BoundVar, Domain, FunctionSymbol, Group, Hypernode, Property, VariableSort

from .distribution import Domain as BoundDomain, Frame, _asserted, _children, _negated_restriction, _negative_universal


MEMBER_KEY = 'russian_grammar.distribution_member'
CLASS_KEY = 'russian_grammar.distribution_class'
SOURCE = 'grammar.distribution_source'
FORMULA = 'grammar.distribution_formula'
DOMAIN_KIND = 'russian_grammar.distribution_domain'


def _pattern(core, name, arguments, source, **meta):
    predicate = core.ensure_abstract_symbol('russian_grammar.distribution.' + name)
    roles = tuple(arguments)
    template = next((t for t in core.store.find_templates_by_predicate(predicate.uid)
                     if t.roles == roles and core.store.domain_of(t.uid) == Domain.H), None)
    if template is None:
        template = core.add_template(Domain.H, core.ref(predicate.uid), roles)
    node, _ = core.add_hypernode(Domain.H, core.ref(template.uid), arguments, 1.0,
                                 meta={'semantic_scope': 'QUANTIFIED', 'source_scope': source, **meta},
                                 count_occurrence=False)
    return core.ref(node.uid)


def _function(core, operator, *operands):
    return core.ref(core.add_function(Domain.H, operator, operands).uid)


def _simple_class(rows, domain, quantifier_negated=False):
    if domain.members or domain.marker is None or rows[domain.marker]['lemma'] not in ('каждый', 'всякий'):
        return None
    if domain.marker == domain.head or rows[domain.marker]['head'] != domain.head:
        return None
    for i, row in enumerate(rows):
        if row['head'] not in (domain.head, domain.marker) or i == domain.marker or row['role'] == 'punctuation':
            continue
        if quantifier_negated and i + 1 == domain.marker and row['role'] == 'particle' and row['lemma'] == 'не':
            continue
        return None
    return rows[domain.head]['lemma']


def _valid_size(members, size):
    return (len(set(members)) == len(members)
            and (size is None or type(size) is int and 0 <= len(members) <= size))


def _share_members(members, head, children):
    nodes = [head]
    seen = {head}
    for node in nodes:
        for child in children[node]:
            if child in seen:
                raise ValueError('DISTRIBUTION_CYCLIC_SHARE')
            nodes.append(child)
            seen.add(child)
    return tuple(members[i] for i in sorted(nodes))


def _variable(number, domain):
    return BoundVar(number, VariableSort.TIME if domain.role in ('time', 'duration') else VariableSort.ENTITY)


def _role_values(frame, rows, members, children):
    slots = {}
    for n, domain in enumerate(frame.domains):
        role = ActantRole.__members__.get(domain.role.upper(), ActantRole.SURFACE_ARG)
        slots.setdefault(role, []).append((_variable(n, domain), members[domain.head]))
    values = {role: pairs[0][0] if len(pairs) == 1 else pairs for role, pairs in slots.items()}
    bound_heads = {domain.head for domain in frame.domains}
    for j in children[frame.predicate]:
        role = ActantRole.__members__.get(rows[j]['role'].upper())
        if role in (ActantRole.SUBJECT, ActantRole.OBJECT, ActantRole.RECIPIENT) and j not in bound_heads and j != frame.share:
            values.setdefault(role, members[j])
    return values


def write(core, observation, members, rows, frames):
    children = _children(rows)
    for frame in frames:
        if not frame.resolved:
            continue
        restrictions = []
        variables = []
        for n, domain in enumerate(frame.domains):
            if not _valid_size(domain.members, domain.cardinality):
                raise ValueError('DISTRIBUTION_MEMBERS_EXCEED_CARDINALITY')
            class_name = _simple_class(rows, domain, frame.quantifier_negated)
            properties = {CLASS_KEY: Property(CLASS_KEY, class_name, 'str')} if class_name else {}
            group = core.add_group(Domain.H, tuple(members[j] for j in domain.members), properties,
                                   {'kind': DOMAIN_KIND, 'head': domain.head, 'marker': domain.marker,
                                    'role': domain.role, 'cardinality': domain.cardinality})
            group_ref = core.ref(group.uid)
            core.add_link(SOURCE, group_ref, core.ref(observation.uid), 1.0)
            variable = _variable(n, domain)
            variables.append(variable)
            restrictions.append(_pattern(core, 'member', {ActantRole.SUBJECT: variable, ActantRole.OBJECT: group_ref},
                                         observation.uid))
        operands = _role_values(frame, rows, members, children)
        for role, value in operands.items():
            if isinstance(value, list):
                uses = tuple(_pattern(core, 'bound_position', {ActantRole.OBJECT: var, ActantRole.SURFACE_ARG: source},
                                      observation.uid) for var, source in value)
                operands[role] = core.ref(core.add_group(Domain.H, uses).uid)
        if frame.share is not None:
            share = core.add_group(Domain.H, _share_members(members, frame.share, children),
                                   meta={'kind': 'russian_grammar.distributed_share'})
            operands[ActantRole.AMOUNT] = core.ref(share.uid)
        predicate = _pattern(core, rows[frame.predicate]['lemma'] + '.body', operands,
                             f'{observation.uid}/{frame.predicate}', predicate=frame.predicate,
                             share=frame.share, marker=frame.marker)
        condition = restrictions[0] if len(restrictions) == 1 else _function(core, 'AND', *restrictions)
        if frame.predicate_negated:
            predicate = _function(core, 'NOT', predicate)
        body = _function(core, 'IMPLIES', condition, predicate)
        for variable in reversed(variables):
            body = _function(core, 'FORALL', variable, body)
        if frame.quantifier_negated:
            body = _function(core, 'NOT', body)
        core.add_link(FORMULA, core.ref(observation.uid), body, 1.0)


def _has_pattern(store, node, name, source):
    if not isinstance(node, Hypernode) or node.meta.get('source_scope') != source or node.meta.get('semantic_scope') != 'QUANTIFIED':
        return False
    template = store.get_template(node.template.uid)
    symbol = store.get_symbol(template.predicate.uid)
    return set(template.roles) == set(node.actants) and 'russian_grammar.distribution.' + name in symbol.forms


def _share_attached(rows, frame):
    share = rows[frame.share]
    if frame.marker is None:
        return share['head'] == frame.predicate
    marker = rows[frame.marker]
    if marker['role'] == 'preposition' and marker['lemma'] == 'на':
        return (share['head'] == frame.predicate and marker['head'] in (frame.share, frame.predicate)
                and any(rows[d.head]['head'] == frame.marker for d in frame.domains))
    if marker['lemma'] != 'по':
        return False
    if marker.get('rule') == 'NUM.DISTR':
        return marker['head'] == frame.share and share['head'] == frame.predicate
    return (marker['role'] == 'preposition' and marker['head'] == frame.predicate
            and share['role'] == 'governed' and share['head'] == frame.marker)


def _body_matches(store, obs, rows, frame, node):
    predicate = rows[frame.predicate]
    children = _children(rows)
    scoped = _negative_universal(rows, children, frame.predicate)
    if frame.predicate_negated or frame.quantifier_negated or scoped is not None:
        if scoped != frame:
            return False
    elif not _asserted(predicate) or _negated_restriction(rows, children, frame.predicate):
        return False
    if not _has_pattern(store, node, predicate['lemma'] + '.body', f'{obs.uid}/{frame.predicate}'):
        return False
    expected = _role_values(frame, rows, obs.members, children)
    if frame.share is not None:
        share = store.get_element(Domain.H, node.actants[ActantRole.AMOUNT].uid)
        if (not isinstance(share, Group) or share.meta.get('kind') != 'russian_grammar.distributed_share'
                or share.members != _share_members(obs.members, frame.share, children)):
            return False
        if not _share_attached(rows, frame):
            return False
        expected[ActantRole.AMOUNT] = node.actants[ActantRole.AMOUNT]
    if set(expected) != set(node.actants):
        return False
    for role, value in expected.items():
        actual = node.actants[role]
        if isinstance(value, list):
            group = store.get_element(Domain.H, actual.uid)
            if not isinstance(group, Group) or len(group.members) != len(value):
                return False
            for member, (var, source) in zip(group.members, value):
                position = store.get_hypernode(member.uid)
                if (not _has_pattern(store, position, 'bound_position', obs.uid)
                        or position.actants != {ActantRole.OBJECT: var, ActantRole.SURFACE_ARG: source}):
                    return False
        elif value != actual:
            return False
    return True


def _unpack(store, observation, root, indices, rows):
    variables = []
    term = store.get_element(Domain.H, root.uid)
    outer = isinstance(term, FunctionSymbol) and term.function_id == 'NOT'
    if outer:
        operand, = term.operands
        term = store.get_element(Domain.H, operand.uid)
    while isinstance(term, FunctionSymbol) and term.function_id == 'FORALL':
        var, body = term.operands
        if not isinstance(var, BoundVar) or var.local_id != len(variables):
            return None
        variables.append(var)
        term = store.get_element(Domain.H, body.uid)
    if not variables or not isinstance(term, FunctionSymbol) or term.function_id != 'IMPLIES':
        return None
    antecedent, consequent = term.operands
    pattern = store.get_element(Domain.H, consequent.uid)
    negative = isinstance(pattern, FunctionSymbol) and pattern.function_id == 'NOT'
    if negative:
        operand, = pattern.operands
        pattern = store.get_element(Domain.H, operand.uid)
    if not isinstance(pattern, Hypernode):
        return None
    condition = store.get_element(Domain.H, antecedent.uid)
    atoms = condition.operands if isinstance(condition, FunctionSymbol) and condition.function_id == 'AND' else (antecedent,)
    if len(atoms) != len(variables):
        return None
    domains = []
    domain_refs = []
    for variable, atom in zip(variables, atoms):
        node = store.get_hypernode(atom.uid)
        if not _has_pattern(store, node, 'member', observation.uid) or node.actants.get(ActantRole.SUBJECT) != variable:
            return None
        group = store.get_element(Domain.H, node.actants[ActantRole.OBJECT].uid)
        if not isinstance(group, Group) or group.meta.get('kind') != DOMAIN_KIND:
            return None
        if store.find_link(SOURCE, group.uid, observation.uid) is None:
            return None
        member_ids = tuple(indices.get(ref.uid) for ref in group.members)
        size = group.meta['cardinality']
        if None in member_ids or not _valid_size(member_ids, size):
            return None
        domain_refs.append(group.uid)
        domains.append(BoundDomain(head=group.meta['head'], role=group.meta['role'], members=member_ids,
                                   cardinality=size, marker=group.meta['marker']))
    frame = Frame(predicate=pattern.meta['predicate'], domains=tuple(domains), share=pattern.meta['share'],
                  marker=pattern.meta['marker'], predicate_negated=negative, quantifier_negated=outer)
    required = [frame.predicate, *(domain.head for domain in domains)]
    optional = [frame.marker, frame.share, *(domain.marker for domain in domains)]
    required.extend(i for i in optional if i is not None)
    if any(type(i) is not int or not 0 <= i < len(rows) for i in required):
        return None
    if any(var != _variable(i, domain) or rows[domain.head]['role'] != domain.role
           for i, (var, domain) in enumerate(zip(variables, domains))):
        return None
    if not _body_matches(store, observation, rows, frame, pattern):
        return None
    return frame, domain_refs


def _records(core, observation):
    indices = {member.uid: j for j, member in enumerate(observation.members)}
    store = core.store
    try:
        rows = tuple(store.get_element(Domain.H, member.uid).meta for member in observation.members)
        for ref, row in zip(observation.members, rows):
            if row['head'] is not None:
                parent = observation.members[row['head']]
                if store.find_link('grammar.' + row['role'], ref.uid, parent.uid) is None:
                    return
    except (KeyError, IndexError, TypeError, AttributeError):
        return
    for edge in store.outgoing_links(observation.uid, FORMULA):
        try:
            item = _unpack(store, observation, edge.target, indices, rows)
        except (KeyError, IndexError, TypeError, AttributeError, ValueError):
            continue
        if item is not None:
            yield *item, rows


def read(core, observation):
    return tuple(frame for frame, _, _ in _records(core, observation))


def _bound_domains(core, domain):
    if domain.meta.get('kind') != DOMAIN_KIND:
        return
    for edge in core.store.outgoing_links(domain.uid, SOURCE):
        try:
            obs = core.store.get_element(Domain.H, edge.target.uid)
        except KeyError:
            continue
        if obs.meta.get('kind') != 'russian_grammar.observation':
            continue
        for frame, refs, rows in _records(core, obs):
            for i, uid in enumerate(refs):
                if uid == domain.uid:
                    yield obs, rows, frame, i


def lookup(core, name):
    for ref in core.store.find_elements_with_property(MEMBER_KEY, name):
        for group in core.store.groups_containing(ref.uid):
            for obs, rows, frame, i in _bound_domains(core, group):
                hits = [j for j in frame.domains[i].members if rows[j]['lemma'] == name]
                if len(hits) != 1 or obs.members[hits[0]] != ref:
                    continue
                member = hits[0]
                morphology = rows[member].get('morphology') or {}
                if morphology.get('pos') != 'NOUN' or morphology.get('number') != 'sing':
                    continue
                if any(r.get('head') == member and r.get('role') == 'numeral' for r in rows):
                    continue
                yield obs, rows, frame, i, member


def lookup_class(core, name):
    for ref in core.store.find_elements_with_property(CLASS_KEY, name):
        group = core.store.get_element(Domain.H, ref.uid)
        for obs, rows, frame, i in _bound_domains(core, group):
            if _simple_class(rows, frame.domains[i], frame.quantifier_negated) == name:
                yield obs, rows, frame, i
