from dataclasses import dataclass

from .morphology import NOMINAL_ROLES, PREDICATE_ROLES


@dataclass(frozen=True)
class Domain:
    head: int
    role: str
    members: tuple[int, ...]
    cardinality: int | None
    marker: int | None


@dataclass(frozen=True)
class Frame:
    predicate: int
    domains: tuple[Domain, ...]
    share: int | None
    marker: int | None
    alternatives: tuple[Domain, ...] = ()
    optional: bool = False
    predicate_negated: bool = False
    quantifier_negated: bool = False

    @property
    def resolved(self):
        return bool(self.domains) and not self.alternatives and not self.optional


@dataclass(frozen=True)
class Mode:
    predicate: int
    marker: int
    kind: str
    argument: int | None


def _children(rows):
    children = [[] for _ in rows]
    for i, row in enumerate(rows):
        if row.get('head') is not None:
            children[row['head']].append(i)
    return children


def _asserted(row):
    return (row['role'] in PREDICATE_ROLES and row.get('assertion_status') == 'asserted'
            and not row.get('scope') and 'quotation' not in row)


def modes(rows):
    children = _children(rows)
    result = []
    for predicate, row in enumerate(rows):
        if not _asserted(row):
            continue
        for j in children[predicate]:
            child = rows[j]
            if child['role'] == 'adverb' and child['lemma'] == 'поровну':
                result.append(Mode(predicate, j, 'equal_shares', None))
            elif child.get('rule') == 'NUM.SUBGROUP' and child.get('quantity_kind') == 'collective':
                markers = [k for k in children[j] if rows[k].get('rule') == 'NUM.SUBGROUP' and rows[k]['lemma'] == 'по']
                if len(markers) == 1:
                    result.append(Mode(predicate, markers[0], 'subgroup_size', j))
            elif child['role'] == 'preposition' and child['lemma'] == 'по':
                governed = [k for k in children[j] if rows[k]['role'] == 'governed']
                if len(governed) == 1:
                    head, = governed
                    part = rows[head]
                    if (part['lemma'] == 'очередь' and part.get('case') == 'datv' and not children[head]
                            and (part.get('morphology') or {}).get('number') == 'sing'):
                        result.append(Mode(predicate, j, 'successive_candidate', head))
    return tuple(result)


def _numeric(rows, children, head):
    if rows[head].get('quantity_kind'):
        return head
    return next((j for j in children[head] if rows[j]['role'] == 'numeral'), None)


def _size(row):
    value = row.get('quantity') or ''
    if (row.get('quantity_kind') in ('cardinal', 'collective', 'both') and value.isdecimal()
            and row.get('quantity_modifier') in (None, 'exact')):
        return int(value)
    return None


def _coordination(rows, children, anchor):
    members = [anchor]
    additive = False
    for member in members:
        if rows[member].get('scope') not in (None, 'universal'):
            return None
        for j in children[member]:
            row = rows[j]
            if (row.get('scope') in ('focus_negated', 'negative', 'alternative', 'negative_coordination')
                    or row['role'] == 'particle' and row['lemma'] == 'не'):
                return None
            if row['role'] == 'nominal_conjunct':
                members.append(j)
            if row['role'] == 'coordinator':
                if row.get('scope') != 'addition' and (row.get('scope') or row['lemma'] != 'и'):
                    return None
                additive = True
    if len(members) > 1 and not additive:
        return None
    return tuple(members) if len(members) > 1 else ()


def _universal_marker(rows, children, head):
    return next((j for j in children[head] if rows[j]['role'] == 'attribute'
                 and rows[j].get('scope') == 'universal' and rows[j]['lemma'] in ('каждый', 'всякий')), None)


def _domain(rows, children, head):
    row = rows[head]
    if (row['role'] not in NOMINAL_ROLES or row.get('assertion_status') != 'asserted'
            or row.get('scope') not in (None, 'universal') or 'quotation' in row):
        return None
    explicit = _universal_marker(rows, children, head)
    anchor = head
    if row.get('rule') == 'NP.PARTITIVE' and row['lemma'] == 'каждый':
        explicit = head
        for prep in children[head]:
            if rows[prep]['role'] == 'preposition' and rows[prep]['lemma'] == 'из':
                antecedents = [rows[j].get('antecedent') for j in children[prep] if rows[j]['role'] == 'governed']
                if len(antecedents) == 1 and antecedents[0] in children[head]:
                    anchor = antecedents[0]
    listed = [j for j in children[head] if rows[j].get('rule') in ('NP.ENUM', 'NP.SUBSET')
              and rows[j]['role'] == 'apposition']
    if len(listed) > 1:
        return None
    if listed:
        anchor = listed[0]
    members = _coordination(rows, children, anchor)
    if members is None:
        return None
    if listed and not members:
        members = (anchor,)
    numeral = _numeric(rows, children, head)
    cardinality = _size(rows[numeral]) if numeral is not None else None
    if explicit is None and not members and cardinality in (None, 0, 1):
        if numeral is not None or (row.get('morphology') or {}).get('number') != 'plur':
            return None
    return Domain(head, row['role'], members, cardinality, explicit if explicit is not None else numeral)


def _explicit(rows, domain):
    return domain.marker is not None and rows[domain.marker]['lemma'] in ('каждый', 'всякий')


def _share(rows, children, predicate, prep):
    governed = [j for j in children[prep] if rows[j]['role'] == 'governed']
    if len(governed) != 1:
        return None
    head, = governed
    numeral = _numeric(rows, children, head)
    row = rows[head]
    if numeral is not None:
        if rows[numeral].get('quantity_kind') not in ('cardinal', 'collective', 'both', 'range', 'fraction', 'indefinite'):
            return None
        if row.get('case') == 'accs':
            return head, False
    if row.get('case') != 'datv':
        return None
    from .distribution_questions import measure_unit
    if numeral is not None and measure_unit(rows[predicate]['lemma'], row['lemma']):
        return head, False
    if numeral is None and (row.get('morphology') or {}).get('number') != 'sing':
        return None
    from .temporal_groups import _unit

    if ((rows[predicate].get('morphology') or {}).get('transitivity') == 'tran'
            and not any(rows[j]['role'] == 'object' for j in children[predicate]) or _unit(row['lemma'])):
        return head, True
    return None


def _aggregate(rows, children, child):
    row = rows[child]
    if row['role'] == 'adverb':
        return row['lemma'] in ('вместе', 'суммарно', 'совокупно', 'совместно')
    if row['role'] != 'preposition' or row['lemma'] != 'в':
        return False
    for head in children[child]:
        noun = rows[head]
        if noun['role'] != 'governed' or noun.get('case') not in ('loct', 'loc2'):
            continue
        if noun['lemma'] in ('сумма', 'совокупность'):
            return True
        if noun['lemma'] == 'сложность' and any(rows[j]['role'] == 'attribute' and rows[j]['lemma'] == 'общий'
                                                for j in children[head]):
            return True
    return False


def _per_unit(rows, children, prep):
    governed = [j for j in children[prep] if rows[j]['role'] == 'governed']
    if len(governed) != 1:
        return None
    head, = governed
    row = rows[head]
    if row.get('case') != 'accs':
        return None
    domain = _domain(rows, children, head)
    if domain and _explicit(rows, domain):
        return domain
    form = row.get('morphology') or {}
    if form.get('number') != 'sing' or form.get('pos') != 'NOUN' or children[head] or row['surface'] != row['surface'].lower():
        return None
    return Domain(head, row['role'], (), None, prep)


def _negated_restriction(rows, children, predicate):
    return any(rows[j].get('scope') == 'focus_negated' and _universal_marker(rows, children, j) is not None
               for j in children[predicate])


def _negative_universal(rows, children, predicate):
    row = rows[predicate]
    if row['role'] != 'predicate' or row['head'] is not None or 'quotation' in row or row.get('assertion_context'):
        return None
    negative = row.get('scope') == 'negated' and row.get('assertion_status') == 'negated'
    if not negative and not _asserted(row):
        return None
    subjects = [j for j in children[predicate] if rows[j]['role'] == 'subject']
    if len(subjects) != 1:
        return None
    subject, = subjects
    marker = _universal_marker(rows, children, subject)
    if marker is None or (rows[subject].get('morphology') or {}).get('pos') != 'NOUN':
        return None
    outer = rows[subject].get('scope') == 'focus_negated'
    if not negative and not outer:
        return None
    if rows[subject].get('scope') not in (None, 'focus_negated'):
        return None
    nominal = {j for j in children[subject] if rows[j]['role'] != 'punctuation'}
    if outer:
        particle = marker - 1
        if (particle not in nominal or rows[particle]['role'] != 'particle' or rows[particle]['lemma'] != 'не'):
            return None
        nominal.remove(particle)
    if nominal != {marker} or children[marker]:
        return None
    negations = []
    for j in children[predicate]:
        part = rows[j]
        if j == subject or part['role'] == 'punctuation':
            continue
        if part['role'] == 'particle' and part['lemma'] == 'не':
            negations.append(j)
        elif (part['role'] not in ('object', 'recipient') or part.get('scope') or part.get('quantity_kind')
              or any(rows[k]['role'] != 'punctuation' for k in children[j])):
            return None
    if negative != bool(negations) or negations and (len(negations) != 1 or marker > negations[0]):
        return None
    domain = Domain(subject, 'subject', (), None, marker)
    return Frame(predicate, (domain,), None, None, predicate_negated=negative, quantifier_negated=outer)


def frames(rows):
    children = _children(rows)
    result = []
    for predicate, row in enumerate(rows):
        negative = _negative_universal(rows, children, predicate)
        if negative is not None:
            result.append(negative)
            continue
        if not _asserted(row) or _negated_restriction(rows, children, predicate):
            continue
        candidates = []
        shares = []
        amounts = []
        prep_sites = []
        unit_domains = {}
        for child in children[predicate]:
            part = rows[child]
            if part['role'] == 'preposition':
                if part['lemma'] == 'по' and (share := _share(rows, children, predicate, child)):
                    shares.append((child, *share))
                else:
                    prep_sites.append(child)
                continue
            share_marker = next((j for j in children[child] if rows[j].get('rule') == 'NUM.DISTR'), None)
            if share_marker is not None:
                shares.append((share_marker, child, False))
                continue
            if part['role'] == 'object' and _numeric(rows, children, child) is not None:
                amounts.append(child)
            if domain := _domain(rows, children, child):
                candidates.append(domain)
        counted = [head for _, head, _ in shares] or amounts
        for head in counted:
            prep_sites.extend(j for j in children[head] if rows[j]['role'] == 'preposition' and rows[j]['lemma'] == 'на')
        has_share = bool(shares)
        for prep in prep_sites:
            if rows[prep]['lemma'] == 'на' and len(counted) == 1 and (unit := _per_unit(rows, children, prep)):
                candidates.append(unit)
                if not has_share:
                    shares.append((prep, counted[0], not _explicit(rows, unit)))
                    unit_domains[prep] = unit
                continue
            for j in children[prep]:
                domain = _domain(rows, children, j)
                if domain and _explicit(rows, domain):
                    candidates.append(domain)
        explicit = tuple(d for d in candidates if _explicit(rows, d))
        grouped_subject = any(_aggregate(rows, children, j) for j in children[predicate])
        if not shares and explicit:
            amount = amounts[0] if len(amounts) == 1 and all(d.head != amounts[0] for d in explicit) else None
            result.append(Frame(predicate, explicit, amount, None))
        for marker, share, optional in shares:
            unit = unit_domains.get(marker)
            required = (*explicit, unit) if unit is not None and unit not in explicit else explicit
            implicit = tuple(d for d in candidates if d not in required and d.head != share
                             and not (grouped_subject and d.role == 'subject'))
            if unit is not None:
                implicit = ()
            if required and not implicit:
                result.append(Frame(predicate, required, share, marker, optional=optional))
            elif not required and len(implicit) == 1:
                result.append(Frame(predicate, implicit, share, marker, optional=optional))
            else:
                result.append(Frame(predicate, required, share, marker, implicit, optional))
    return tuple(result)
