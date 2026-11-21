from collections.abc import Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass, replace
from fractions import Fraction
from uuid import uuid4

from ah.model import Domain, Property

from .valency import violation
from . import adjuncts
from . import homogeneous, lexical_parts
from .infinitives import FRAMES
from .morphology import _common, from_tag
from .parser import Result, analyze
from .prepositions import TOKEN
from .rules import dictionary, known_forms



ROOT_KEY = 'russian_grammar.root'
CONJUNCT_KEY = 'russian_grammar.conjunct'
RELATIVE_KEY = 'russian_grammar.relative'
GAP_KEY = 'russian_grammar.gap'
CONCESSION_KEY = 'russian_grammar.concession'
UNKNOWN = 'Неизвестно.'
ARGUMENTS = {'subject', 'comparison_standard', 'object', 'recipient', 'experiencer', 'beneficiary', 'stimulus', 'instrument', 'oblique', 'agent'}
AMOUNTS = {'cardinal', 'collective', 'both', 'fraction', 'range', 'indefinite'}
NUMBER_PARTS = {'numeral_part', 'quantity_modifier'}
PERSONAL = {'я': 'speaker', 'ты': 'addressee', 'мы': 'speaker_group', 'вы': 'addressee_group'}
INTERROGATIVES = frozenset('кто что какой который чей сколько где куда откуда когда почему зачем как каков насколько'.split())


@dataclass(frozen=True)
class GrammarReply:
    status: str
    text: str
    observation_ref: str | None = None
    analysis: Result | None = None
    support_refs: tuple[str, ...] = ()


def _adapter(core, journal):
    existing = getattr(core, '_formalizer_adapter', None)
    if existing is not None and journal is not None and existing._journal.path.resolve() != journal.path.resolve():
        raise ValueError('AHCore already uses another journal')
    if existing is None and journal is not None:
        from ah.formalizer.ah_adapter import AHStoreAdapter
        return AHStoreAdapter(core.store, journal, core)
    return existing


@contextmanager
def _access(core, adapter, write=False):
    if adapter is not None:
        manager = (adapter.canonical_transaction('russian_grammar:' + uuid4().hex)
                   if write else adapter.canonical_read())
        with manager as view:
            yield view
    else:
        with core.store._lock:
            if write:
                with core.transaction() as view:
                    yield view
            else:
                yield core


def _root(rows):
    return next(i for i, row in enumerate(rows) if row['role'] == 'predicate' and row['head'] is None)


def _rows(result, participants):
    rows = tuple({**asdict(token), **asdict(link)} for token, link in zip(result.tokens, result.analyses[0]))
    for focus in result.confirmed_focus:
        rows[focus.modifier]['focus_offsets'] = [rows[j]['start'] for j in focus.members]
    children = [[] for _ in rows]
    root = _root(rows)
    for i, row in enumerate(rows):
        if row['head'] is not None:
            children[row['head']].append(i)
    contexts = {}
    qualifications = {}
    for i, row in enumerate(rows):
        if (row['role'] == 'parenthetical' and row.get('scope') != 'ordering'
                or row['role'] == 'preposition' and row.get('scope') == 'qualification'):
            qualifications[row['head']] = 'qualified'
        if (row['role'] != 'clause_marker' or not row.get('scope')
                or row['rule'] == 'PAIR.MARK' and row['scope'] in ('addition', 'negative_coordination')):
            continue
        host = row['head']
        contexts[host] = row['scope']
        qualification = {'condition': 'conditional', 'concessive_condition': 'conditional', 'alternative': 'alternative',
                         'adverbial': 'adverbial'}.get(row['scope'])
        if qualification and rows[host]['head'] is not None:
            qualifications[rows[host]['head']] = qualification
    pending = [(root, None, 'asserted')]
    while pending:
        i, enclosing, governing_status = pending.pop()
        row = rows[i]
        if row['rule'] == 'V3.DAT.UNBOUND':
            row['lemma_alternatives'] = sorted({lemma for lemma, tag in known_forms(row['surface'])
                                                if tag.POS == 'NPRO' and tag.person == '3per' and tag.case == 'datv'})
        if (row['scope'] or '').split('_', 1)[0] == 'title' and row['role'] in ('apposition', 'nominal_conjunct', 'genitive_modifier', 'governed'):
            row['quotation'] = i
            enclosing = governing_status = 'title'
        elif row['rule'] == 'UTT.QUOTE':
            row['quotation'] = i
        elif row['head'] is not None and 'quotation' in rows[row['head']]:
            row['quotation'] = rows[row['head']]['quotation']
        if row['rule'] == 'PART.SUBSTANTIVE':
            if governing_status == 'asserted':
                enclosing = enclosing or 'attributive'
                governing_status = enclosing
        if row['rule'] == 'PAREN.EXPL':
            enclosing = enclosing or 'parenthetical'
            governing_status = enclosing
        scope = row.get('scope') or ''
        category, _, polarity = scope.partition('_')
        if category in ('negated', 'averted'):
            category, polarity = '', category
        role = row['role']
        boundary = contexts.get(i)
        factual_concession = role == 'clause_adverbial' and boundary == 'concession'
        if factual_concession:
            row['clause_relation'] = boundary
            boundary = None
            if category == 'concession':
                category = ''

        if role == 'converb':
            from .converb_control import needs_confirmation
            if needs_confirmation(result.analyses[0], i):
                boundary = 'qualified'
        if role == 'clause_relative' and row['rule'] == 'CL.REL' and not category:
            nominal = row['head']
            if governing_status != 'asserted':
                boundary = governing_status
            elif (rows[nominal].get('scope') == 'focus_negated' or
                  any(rows[j].get('scope') in ('universal', 'negative') for j in children[nominal])):
                boundary = 'restrictive'
        if (row.get('morphology') or {}).get('mood') == 'impr':
            boundary = 'directive'
        if role in ('predicate', 'clause_conjunct', 'clause_adverbial', 'clause_complement', 'clause_relative',
                    'converb', 'infinitive', 'participle'):
            boundary = boundary or category
            if role == 'participle':
                boundary = boundary or 'attributive'
            if role in ('clause_adverbial', 'clause_complement', 'infinitive') and not factual_concession:
                boundary = boundary or 'embedded'
            enclosing = enclosing or boundary or qualifications.get(i) or None
            status = enclosing or polarity or 'asserted'
        else:
            status = governing_status
        row['assertion_context'] = enclosing
        row['assertion_status'] = status
        pending.extend((j, enclosing, status) for j in children[i])
    for row in rows:
        deixis = row.get('implicit_subject') or PERSONAL.get(row['lemma'])
        if deixis in PERSONAL.values():
            row['participant_ref'] = None if 'quotation' in row else participants.get(deixis.removesuffix('_group'))
    return rows


def _remember(core, result, rows, source, distributions):
    from . import distribution_graph

    indexed = {index for frame in distributions for domain in frame.domains for index in domain.members}
    root = rows[_root(rows)]
    projected = set(homogeneous.projection_members(rows, _root(rows))) - {_root(rows)}
    members = []
    for i, row in enumerate(rows):
        props = {}
        if i in indexed:
            key = distribution_graph.MEMBER_KEY
            props[key] = Property(key, row['lemma'], 'str')
        parts = lexical_parts.metadata(row['surface'], row['start'], row['lemma'])
        if parts:
            row['lexical_parts'] = list(parts)
        if (row['role'] == 'clause_relative' or row['rule'] == 'GAP') and row['assertion_status'] == 'asserted':
            key = GAP_KEY if row['rule'] == 'GAP' else RELATIVE_KEY
            props[key] = Property(key, row['lemma'], 'str')
        if row.get('clause_relation') == 'concession' and row['assertion_status'] in ('asserted', 'negated'):
            props[CONCESSION_KEY] = Property(CONCESSION_KEY, row['lemma'], 'str')
        if i in projected and row['assertion_status'] == 'asserted':
            props[CONJUNCT_KEY] = Property(CONJUNCT_KEY, row['lemma'], 'str')
        members.append(core.ref(core.add_entity(Domain.H, properties=props, meta=row).uid))
    for i, row in enumerate(rows):
        for key in ('head', 'controller', 'antecedent', 'ellipsis_source', 'coord_head', 'shared_agent', 'shared_object',
                    'distribution_predicate', 'distribution_argument'):
            if row.get(key) is not None:
                relation = 'grammar.' + (row['role'] if key == 'head' else key)
                core.add_link(relation, members[i], members[row[key]], 1.0)
    for focus in result.confirmed_focus:
        anchor = core.add_group(Domain.H, tuple(members[j] for j in focus.members),
                                meta={'kind': 'russian_grammar.focus_anchor'})
        core.add_link('grammar.modifier_scope', members[focus.modifier], core.ref(anchor.uid), 1.0)
    observation = core.add_group(
        Domain.H, tuple(members), {ROOT_KEY: Property(ROOT_KEY, root['lemma'], 'str')},
        {'verbatim': result.source, 'source': source, 'kind': 'russian_grammar.observation',
         'root_status': root['assertion_status']},
    )
    distribution_graph.write(core, observation, members, rows, distributions)
    return observation.uid


def _stored_rows(core, group):
    rows = tuple(core.store.get_element(Domain.H, member.uid).meta for member in group.members)
    for member, row in zip(group.members, rows):
        anchor = row.get('antecedent')
        if not _correlative_reference(row) and not (row['role'] == 'possessive' and anchor is not None):
            continue
        if (anchor is None or not 0 <= anchor < len(rows) or
                core.store.find_link('grammar.antecedent', member.uid, group.members[anchor].uid) is None):
            return None
    return rows


def _lookup(core, lemma):
    for ref in core.store.find_elements_with_property(ROOT_KEY, lemma):
        group = core.store.get_element(Domain.H, ref.uid)
        rows = _stored_rows(core, group)
        if rows is None:
            continue
        root = _root(rows)
        yield group, rows, root
        members = homogeneous.projection_members(rows, root)
        if members and (projection := homogeneous.project(rows, members, root)):
            yield group, *projection
    for ref in core.store.find_elements_with_property(CONJUNCT_KEY, lemma):
        for group in core.store.groups_containing(ref.uid):
            if group.meta.get('kind') != 'russian_grammar.observation':
                continue
            rows = _stored_rows(core, group)
            if rows is None:
                continue
            members = homogeneous.projection_members(rows, _root(rows))
            target = group.members.index(ref)
            if target in members and (projection := homogeneous.project(rows, members, target)):
                yield group, *projection
    for key in (RELATIVE_KEY, GAP_KEY, CONCESSION_KEY):
        for ref in core.store.find_elements_with_property(key, lemma):
            for group in core.store.groups_containing(ref.uid):
                if group.meta.get('kind') == 'russian_grammar.observation':
                    rows = _stored_rows(core, group)
                    if rows is not None:
                        yield group, rows, group.members.index(ref)


def _subject_lookup(core, name, lemma):
    seen = set()
    for uid in core.store.subject_occurrences(name):
        anchor = uid
        visited = {uid}
        while links := core.store.outgoing_links(anchor, 'grammar.nominal_conjunct'):
            if len(links) != 1 or links[0].target.uid in visited:
                break
            anchor = links[0].target.uid
            visited.add(anchor)
        for edge in core.store.outgoing_links(anchor, 'grammar.subject'):
            for group in core.store.groups_containing(edge.target.uid):
                if group.meta.get('kind') != 'russian_grammar.observation':
                    continue
                indices = {member.uid: j for j, member in enumerate(group.members)}
                if not visited.issubset(indices) or (group.uid, uid) in seen:
                    continue
                seen.add((group.uid, uid))
                rows = _stored_rows(core, group)
                if rows is None:
                    continue
                root = _root(rows)
                predicate = indices[edge.target.uid]
                if rows[predicate]['lemma'] == lemma:
                    props = core.store.get_element(Domain.H, edge.target.uid).properties
                    if predicate == root or any(key in props for key in (RELATIVE_KEY, GAP_KEY, CONCESSION_KEY)):
                        yield group, rows, predicate, (indices[uid], indices[anchor])
                members = homogeneous.projection_members(rows, root)
                for target in members:
                    if rows[target]['lemma'] == lemma and (projection := homogeneous.project(rows, members, target)):
                        yield group, *projection, None


def _question_word(word, selected_lemma=None):
    return any((selected_lemma is None or selected_lemma == lemma) and (lemma in INTERROGATIVES or 'Ques' in tag)
               for lemma, tag in known_forms(word))


def _argument_question(word):
    return any(lemma in ('кто', 'что') and tag.POS == 'NPRO' for lemma, tag in known_forms(word))


def _participants(source, speaker_ref=None, addressee_ref=None):
    dialogue = {'user': 'agent', 'agent': 'user'}
    return {'speaker': speaker_ref or (source if source in dialogue else None),
            'addressee': addressee_ref or dialogue.get(source)}


def _attested_form(row, pos):
    if row.get('morphology'):
        return row['morphology']
    forms = [from_tag(tag) for lemma, tag in known_forms(row['surface']) if lemma == row['lemma'] and tag.POS == pos]
    form = _common(forms)
    return asdict(form) if form else {}


def _normalize_short_predicates(rows, result):
    copulas = {row['head']: row for row in rows if row['role'] == 'copula'}
    conditional = {row['head'] for row in rows if row.get('rule') == 'N3'}
    for i, row in enumerate(rows):
        form = row.get('morphology') or {}
        if row.get('rule') != 'V2.PASS' and form.get('pos') != 'PRTS':
            continue
        if form.get('mood') == 'indc':
            continue
        lexical = _attested_form(row, 'PRTS')
        auxiliary = _attested_form(copulas[i], 'VERB') if i in copulas else {}
        tense = auxiliary.get('tense') if i in copulas else 'pres'
        if lexical and tense:
            mood = 'cond' if i in conditional or lexical.get('mood') == 'cond' else 'indc'
            result[i] = dict(result[i], morphology=dict(lexical, tense=tense, person=auxiliary.get('person'), mood=mood))


def _expand_shared_arguments(rows, result, budget):
    shared = [(i, row[key]) for i, row in enumerate(rows) for key in ('shared_agent', 'shared_object')
              if row.get(key) is not None]
    if not shared:
        return True
    children = [[] for _ in rows]
    for i, row in enumerate(rows):
        if row.get('head') is not None and row['role'] != 'punctuation':
            children[row['head']].append(i)
    for predicate, actor in shared:
        copies = {}
        branch = [(actor, predicate)]
        for original, parent in branch:
            if budget == 0:
                return False
            budget -= 1
            occurrence = len(result)
            copies[original] = occurrence
            row = dict(result[original], head=parent, shared_occurrence=original,
                       assertion_context=result[parent].get('assertion_context'),
                       assertion_status=result[parent]['assertion_status'])
            result.append(row)
            branch.extend((child, occurrence) for child in children[original])
        for occurrence in copies.values():
            row = result[occurrence]
            for key in ('controller', 'antecedent', 'ellipsis_source', 'coord_head', 'shared_agent', 'shared_object'):
                if row.get(key) in copies:
                    row[key] = copies[row[key]]
    return True


def _query_rows(rows, participants, budget):
    from .collective_agreement import query_features

    result = list(rows)
    actors = {}
    counted = {row['head']: row for row in rows if row['role'] == 'numeral'}
    for i, row in enumerate(rows):
        if i in counted:
            numeral = counted[i]
            result[i] = dict(row, counted=numeral.get('quantity_kind'))
            if numeral.get('quantity_kind') in ('both', 'cardinal', 'collective') and numeral.get('quantity_modifier') in (None, 'exact'):
                value = numeral.get('quantity')
                if value and value.isdecimal() and value != '0':
                    result[i]['count_number'] = 'sing' if value == '1' else 'plur'
        elif row['role'] in ('attribute', 'possessive') and row['head'] in counted:
            result[i] = dict(row, count_agreement=True)
        implicit = row.get('implicit_subject')
        if implicit in PERSONAL.values() and row['role'] not in ('infinitive', 'converb'):
            pronoun = next(word for word, role in PERSONAL.items() if role == implicit)
            actors[i] = len(result)
            result.append({'role': 'subject', 'head': i, 'surface': pronoun, 'lemma': pronoun, 'case': 'nomn',
                           'assertion_status': row['assertion_status'], 'implicit': True,
                           'participant_ref': row.get('participant_ref')})
        elif row['lemma'] in PERSONAL and 'participant_ref' not in row:
            result[i] = dict(row, participant_ref=participants.get(PERSONAL[row['lemma']].removesuffix('_group')))
    for i, row in enumerate(rows):
        if row['role'] in ('infinitive', 'converb') and row.get('implicit_subject') in PERSONAL.values():
            parent = row['head']
            while parent is not None and parent not in actors:
                parent = rows[parent]['head']
            if parent is not None and rows[parent].get('implicit_subject') == row['implicit_subject']:
                result[i] = dict(row, controller=actors[parent])
        elif row['role'] == 'possessive' and row['lemma'] == 'свой' and row.get('antecedent') is None:
            from .reflexive_possession import EVENT_ROLES

            governor = row['head']
            while governor is not None and rows[governor]['role'] not in EVENT_ROLES:
                governor = rows[governor]['head']
            if governor in actors:
                result[i] = dict(result[i], antecedent=actors[governor])
    for row in rows:
        if row.get('rule') == 'CL.CORRELATE' and row['lemma'] == 'сколько':
            anchor = row['antecedent']
            result[anchor] = dict(result[anchor], correlative_quantity=True)
    query_features(rows, result)
    _normalize_short_predicates(rows, result)
    return result if _expand_shared_arguments(rows, result, budget) else None


def _case(row):
    return (row.get('case') or (row.get('morphology') or {}).get('case') or
            {'subject': 'nomn', 'object': 'accs'}.get(row['role']))


def _quantity_key(row):
    kind = row.get('quantity_kind')
    value = row.get('quantity')
    if kind == 'indefinite' and row['lemma'] != 'столько':
        value = row['lemma']
    return (kind, value, row.get('quantity_modifier') or 'exact') if value is not None else None


def _answers_quantity(question, stored):
    key = _quantity_key(stored)
    qualifier = question.get('quantity_modifier')
    if stored.get('correlative_quantity'):
        return qualifier is None
    if key is None or key[0] not in AMOUNTS:
        return False
    if qualifier == 'exact' and key[0] == 'range':
        return False
    return not qualifier or qualifier == key[2]


def _quantity_matches(row, stored, focus):
    standalone = row['role'] != 'numeral'
    if standalone and _case(row) != _case(stored):
        return False
    if focus and row['quantity_kind'] == 'query':
        if stored.get('counted'):
            return not (stored['counted'] == 'fraction' and (stored.get('morphology') or {}).get('number') == 'plur')
        return _answers_quantity(row, stored)
    if standalone:
        left, right = row.get('morphology') or {}, stored.get('morphology') or {}
        if any(left.get(k) and right.get(k) and left[k] != right[k] for k in ('gender', 'animacy', 'number')):
            return False
    key = _quantity_key(row)
    return key is not None and key == _quantity_key(stored)


def _participant_answer(row):
    ref = row.get('participant_ref')
    if ref is None:
        return None
    label = {'user': 'Пользователь', 'agent': 'Агент'}.get(ref, ref)
    case = _case(row)
    if case and case != 'nomn':
        if ref not in ('user', 'agent') or row['lemma'] in ('мы', 'вы'):
            return f"«{row['surface']}» ({label})"
        for form in dictionary().parse(label):
            if form.tag.POS == 'NOUN' and form.tag.animacy == 'anim':
                inflected = form.inflect({case, 'sing'})
                if inflected:
                    return inflected.word.capitalize()
    if row['lemma'] == 'мы':
        return label + ' и другие'
    return label if row['lemma'] != 'вы' else 'Адресат обращения «вы» (' + label + ')'


def _quantity_answer_head(question, stored, children, head):
    group = stored[head]['head'] if stored[head]['role'] == 'numeral' else head
    for j in children[group]:
        if (stored[j]['role'] == 'nominal_conjunct' and
                (question['role'] != 'numeral' or stored[j]['lemma'] == stored[group]['lemma'])):
            return None
    if not stored[head].get('counted'):
        return head
    amounts = [j for j in children[head] if stored[j]['role'] == 'numeral' and _answers_quantity(question, stored[j])]
    return amounts[0] if len(amounts) == 1 else None


def _nominal_parts(stored, children, head):
    parts = [head]
    paired = any(stored[i].get('rule') == 'PAIR.MARK' for i in children[head])
    parent = stored[head]['head']
    expanded = stored[head].get('rule') in ('GAP.OBJ', 'GAP.SUBJ', 'NEG.EXIST.OWNER', 'NEG.EXIST.ENTITY')
    if parent is not None:
        expanded = expanded or any(stored[i].get('rule') == 'GAP' for i in children[parent])
    modifiers = set()
    for j in parts:
        for child in children[j]:
            role = stored[child]['role']
            if j in modifiers or role in ('participle', 'genitive_modifier'):
                modifiers.add(child)
                parts.append(child)
            elif (stored[child].get('rule') == 'F.NP' and stored[j]['role'] in ('attribute', 'possessive')
                  or stored[child].get('rule') == 'NP.DET' or role == 'possessive' and stored[child]['lemma'] == 'свой'
                  or role in NUMBER_PARTS or role in ('name_part', 'nominal_conjunct', 'coordinator', 'numeral') or
                  paired and (role == 'coordinator_part' or role in ('attribute', 'possessive')) or
                  (expanded or stored[j].get('counted')) and role in ('attribute', 'possessive')):
                parts.append(child)
    if parent is not None and stored[head]['role'] == 'numeral' and stored[head].get('quantity_modifier'):
        parts.extend(i for i in children[parent] if stored[i]['rule'] == 'NUM.BOUND')
    return parts


def _nominal_answer(stored, parts, source):
    parts = {stored[i].get('shared_occurrence', i) for i in parts}
    words = []
    identity = []
    for j in sorted(parts):
        row = stored[j]
        word = _participant_answer(row) if row['lemma'] in PERSONAL else row['surface']
        if row.get('rule') == 'GAP.NOUN':
            from .ellipsis import noun_surface
            word = noun_surface(row, stored)
        if word is None:
            return None
        words.append(word)
        if row.get('quantity_kind') and row['role'] not in NUMBER_PARTS:
            identity.append(_quantity_key(row) or word.casefold())
        elif row['role'] not in NUMBER_PARTS:
            identity.append(word.casefold())
    phrase = ' '.join(words)
    if any(stored[j]['role'] in ('participle', 'genitive_modifier') or stored[j].get('quantity_kind') == 'range'
           or stored[j].get('rule') == 'PAIR.MARK' for j in parts):
        ordered = sorted(parts)
        first, last = ordered[0], ordered[-1]
        included = set(parts)
        if (all(j in included or stored[j]['role'] == 'punctuation' for j in range(first, last + 1)) and
                all(word == stored[j]['surface'] for word, j in zip(words, ordered))):
            phrase = source[stored[first]['start']:stored[last]['end']]
    return tuple(identity), phrase


def _may_deny_participation(row):
    if row.get('scope') in ('universal', 'negative', 'focus_negated', 'focus_exclusive'):
        return True
    if row['lemma'] in ('никто', 'ничто', 'никакой', 'ничей', 'нисколько', 'ни', 'не'):
        return True
    kind = row.get('quantity_kind')
    if not kind or kind == 'ordinal':
        return False
    if kind == 'indefinite':
        return row['lemma'] not in ('несколько', 'много')
    qualifier = row.get('quantity_modifier')
    if qualifier in ('at_most', 'upper_bound', 'less_than', 'approximate', 'negative_concord'):
        return True
    try:
        lower = Fraction((row.get('quantity') or '').partition('..')[0])
    except (ValueError, ZeroDivisionError):
        return True
    return lower < 0 if qualifier == 'more_than' else lower <= 0


def _projection_requirements(rows, children, root, scoped):
    required = set()
    subtree = _descendants(children, [root])
    if rows[root].get('rule') in ('NEG.EXIST', 'V3.UNAVAILABLE'):
        required.update(subtree)
    if any(rows[j]['role'] == 'coordinator' and rows[j].get('scope') == 'alternative' for j in subtree):
        required.update(subtree)
    for child in children[root]:
        argument = rows[child]['role'] in ARGUMENTS
        if not argument and not scoped:
            continue
        branch = [child]
        modifiers = set()
        for node in branch:
            if rows[node]['role'] in ('participle', 'genitive_modifier') or rows[node]['head'] in modifiers:
                modifiers.add(node)
            branch.extend(children[node])
        nominal = ('attribute', 'possessive', 'name_part', 'numeral')
        if (scoped and (not argument or any(node not in modifiers and rows[node]['role'] not in nominal for node in branch[1:])) or
                any(node not in modifiers and _may_deny_participation(rows[node]) for node in branch)):
            required.update(branch)
        elif scoped or any(_may_deny_participation(rows[node]) for node in modifiers):
            required.update(modifiers)
    return required


def _descendants(children, roots):
    branch = list(roots)
    for node in branch:
        branch.extend(children[node])
    return set(branch)


def _coord_anchor(rows, i):
    anchor = rows[i].get('coord_head')
    return i if anchor is None else anchor


def _participle_groups(rows, observed):
    groups = {}
    for i, row in enumerate(rows):
        anchor = row.get('coord_head')
        if row['role'] == 'participle' and anchor is not None:
            groups.setdefault(anchor, {anchor}).add(i)
    projection = set()
    for anchor, members in groups.items():
        if any(rows[i].get('scope') not in (None, 'negated') for i in members):
            continue
        host = rows[anchor]['head']
        while host is not None:
            row = rows[host]
            if (row['role'] in ('clause_adverbial', 'clause_complement', 'clause_relative', 'infinitive', 'converb') or
                    {'averted', 'negated', 'alternative', 'comparison', 'negative'}.intersection(
                        (row.get('scope') or '').split('_'))):
                break
            if host == observed:
                projection.add(anchor)
                break
            host = row['head']
    return groups, projection


def _omitted_conjuncts(groups, projection, stored, children, covered):
    omitted = set()
    for anchor, members in groups.items():
        remaining = members & covered
        if not remaining or remaining == members:
            continue
        if anchor not in projection:
            return None
        omitted.update(_descendants(children, members - remaining))
        first = min(remaining)
        markers = [i for i in children[first] if stored[i]['role'] == 'coordinator' and
                   stored[i].get('scope') in ('addition', 'correction', 'contrast')]
        omitted.update(_descendants(children, markers))
    return omitted


def _correlative_reference(row):
    return (row.get('rule') in ('CL.SPATIAL.REF', 'CL.CORRELATE') or
            row.get('rule') == 'CL.NOMREF' and row['lemma'] in ('кто', 'что'))


def _correlative_restrictions(stored, children, observed):
    anchors = {}
    participants = {}
    domain = _descendants(children, (observed,))
    for i in domain:
        reference = stored[i]
        anchor = reference.get('antecedent')
        if anchor not in domain or not _correlative_reference(reference):
            continue
        node = reference['head']
        while node is not None and node != anchor:
            row = stored[node]
            if row['role'] == 'clause_relative' and row['head'] == anchor:
                anchors.setdefault(anchor, set()).add(node)
                if reference['rule'] == 'CL.NOMREF':
                    participants.setdefault(anchor, set()).add(reference['lemma'])
                break
            node = row['head']
    return anchors, participants


def _restricted_answer(stored, parts, source):
    original = sorted({stored[i].get('shared_occurrence', i) for i in parts if not stored[i].get('implicit')})
    if not original:
        return None
    groups = []
    first = previous = original[0]
    for i in original[1:]:
        if any(stored[j]['role'] != 'punctuation' for j in range(previous + 1, i)):
            groups.append(source[stored[first]['start']:stored[previous]['end']])
            first = i
        previous = i
    groups.append(source[stored[first]['start']:stored[previous]['end']])
    return tuple(stored[i]['surface'].casefold() for i in original), ', '.join(groups)


def _extraction(rows, stored, observed, source, focus, budget, subject_member=None):
    root = _root(rows)
    if any(row.get('implicit_subject') == 'unresolved' and (focus is None or i != root) for i, row in enumerate(rows)):
        return {}
    scoped_question = focus is not None and bool(rows[root].get('scope')) and rows[root]['rule'] not in ('NEG.EXIST', 'V3.UNAVAILABLE')
    concord = rows[root].get('scope') == 'negated' and any(
        row.get('rule') == 'PAIR.MARK' and row.get('scope') == 'negative_coordination' for row in stored)
    if scoped_question and not concord and not any(row['role'] == 'clause_marker' and row.get('scope') in ('condition', 'concessive_condition', 'adverbial')
                                   for row in rows):
        return {}
    children = [[] for _ in rows]
    for i, row in enumerate(rows):
        if row['head'] is not None and row.get('rule') != 'UTT.POLAR' and row['role'] != 'punctuation' and row['role'] not in NUMBER_PARTS and row.get('scope') != 'ordering':
            children[row['head']].append(i)
    surface_children = [[] for _ in stored]
    for j, row in enumerate(stored):
        if row['head'] is not None and row['role'] != 'punctuation':
            surface_children[row['head']].append(j)
    children_found = [[j for j in group if stored[j]['role'] not in NUMBER_PARTS and stored[j].get('scope') != 'ordering']
                      for group in surface_children]
    if subject_member is not None:
        member, anchor = subject_member
        children_found[observed] = [member if j == anchor else j for j in children_found[observed]]
        children_found[member] = []
    if not scoped_question and not any(row['role'] == 'clause_relative' for row in rows):
        children_found = [[j for j in group if stored[j]['role'] != 'clause_relative'] for group in children_found]
    if not any(row.get('clause_relation') == 'concession' for row in rows):
        children_found[observed] = [j for j in children_found[observed]
                                    if stored[j].get('clause_relation') != 'concession'
                                    and not (stored[observed].get('clause_relation') == 'concession'
                                             and stored[j].get('scope') == 'concession'
                                             and stored[j]['role'] == 'clause_marker')]
    groups, projection = _participle_groups(stored, observed)
    flexible = {j for anchor in projection for j in (stored[anchor]['head'], *groups[anchor])}
    if focus is not None:
        required = _projection_requirements(stored, children_found, observed, scoped_question)
    else:
        required = _descendants(children_found, [observed]) if projection else set()
    restrictions, participants = _correlative_restrictions(stored, surface_children, observed)
    for anchor, clauses in restrictions.items():
        required.add(anchor)
        required.update(_descendants(surface_children, clauses))
    argument = rows[focus]['head'] if focus is not None and rows[focus]['role'] == 'numeral' else focus
    agreement_target = rows[argument]['head'] if argument is not None and rows[argument]['role'] == 'subject' else None
    order = [root]
    for i in order:
        order.extend(children[i])
    states = [{}]
    for i in order:
        row = rows[i]
        following = []
        for mapping in states:
            pool = [observed] if i == root else children_found[mapping[row['head']]]
            for j in pool:
                if focus is None and j not in flexible and len(children[i]) != len(children_found[j]):
                    continue
                variable_subject = i == agreement_target or (row['role'] in ('auxiliary', 'copula') and
                                                              row['head'] == agreement_target)
                candidate = stored[j]
                if subject_member is not None:
                    if j == member:
                        candidate = {**candidate, 'role': 'subject'}
                    if i == root:
                        variable_subject = True
                if i == root and candidate.get('clause_relation') == 'concession':
                    candidate = {**candidate, 'role': 'predicate',
                                 'scope': None if candidate.get('scope') == 'concession' else candidate.get('scope')}
                if (i == focus and not row.get('scope') and candidate.get('scope') == 'focus_exclusive'
                        and candidate['assertion_status'] == 'asserted'):
                    candidate = {**candidate, 'scope': None}
                if i == focus and candidate.get('rule') == 'CL.NOMREF':
                    target = stored[candidate['antecedent']]
                    candidate = {**candidate, 'relative_animacy': (target.get('morphology') or {}).get('animacy')}
                if j in mapping.values():
                    continue
                if i == focus and j in participants:
                    if (participants[j] != {row['lemma']} or row['role'] != candidate['role']
                            or _case(row) != _case(candidate) or row['assertion_status'] != candidate['assertion_status']):
                        continue
                elif i == focus and adjuncts.question(row):
                    if not adjuncts.matches(row, stored, surface_children, j):
                        continue
                elif not _compatible(rows, i, candidate, i == focus, i == root, variable_subject):
                    continue
                following.append({**mapping, i: j})
                if len(following) > budget:
                    return None
        states = following
        if not states:
            break
    answers = {}
    starts = {row['start']: i for i, row in enumerate(rows) if 'start' in row and 'shared_occurrence' not in row}
    confirmed = [(i, tuple(starts.get(offset) for offset in row['focus_offsets'])) for i, row in enumerate(rows)
                 if row.get('focus_offsets')]
    for mapping in states:
        if any(i not in mapping or any(j not in mapping for j in target)
               or [stored[mapping[j]].get('start') for j in target] != stored[mapping[i]].get('focus_offsets')
               for i, target in confirmed):
            continue
        if any(rows[i].get(key) is not None and mapping.get(rows[i][key]) != stored[j].get(key)
               for i, j in mapping.items() for key in ('controller', 'antecedent')):
            continue
        covered = set(mapping.values())
        if any(_coord_anchor(stored, j) != _coord_anchor(stored, mapping[rows[i]['coord_head']])
               for i, j in mapping.items() if rows[i].get('coord_head') is not None):
            continue
        omitted = _omitted_conjuncts(groups, projection, stored, children_found, covered)
        if omitted is None:
            continue
        missing = required - covered - omitted
        if focus is None:
            if missing:
                continue
            answers['Да.'] = 'Да.'
        elif stored[mapping[focus]].get('rule') in ('CONTENT.EXPL', 'CONTENT.ANCHOR'):
            entry = mapping[focus]
            if stored[entry]['rule'] == 'CONTENT.ANCHOR':
                clauses = [j for j in surface_children[entry] if stored[j]['rule'] == 'CONTENT.EXPL']
                if stored[entry].get('scope') == 'focus_exclusive':
                    missing.difference_update(j for j in surface_children[entry] if stored[j]['rule'] == 'F.NP')
            else:
                clauses = [entry]
            parts = _descendants(surface_children, clauses)
            if len(clauses) == 1 and missing <= parts and (answer := _restricted_answer(stored, parts, source)):
                identity, phrase = answer
                answers[identity] = phrase
        elif stored[mapping[focus]].get('rule') == 'CL.POLAR':
            parts = _descendants(surface_children, [mapping[focus]])
            if missing.issubset(parts) and (answer := _restricted_answer(stored, parts, source)):
                answers[answer[0]] = answer[1]
        elif rows[focus]['role'] == 'possessive' and rows[focus]['lemma'] == 'чей':
            owner = stored[mapping[focus]]['antecedent']
            if owner is not None and not missing:
                parts = _nominal_parts(stored, surface_children, owner)
                if answer := _nominal_answer(stored, parts, source):
                    identity, phrase = answer
                    answers[identity] = phrase
        elif stored[mapping[focus]].get('rule') == 'UTT.QUOTE':
            quote = mapping[focus]
            bounds = [row for row in stored if row.get('rule') == 'UTT.QUOTE.BOUND' and row['head'] == quote]
            if len(bounds) == 2 and all(stored[j].get('quotation') == quote for j in missing):
                phrase = source[min(row['start'] for row in bounds):max(row['end'] for row in bounds)]
                answers[phrase] = phrase
        elif stored[mapping[focus]].get('event_view'):
            if missing:
                continue
            reference = stored[mapping[focus]]
            target = reference['antecedent']
            if reference['event_view'] == 'event' and 'averted' in (stored[target].get('scope') or '').split('_'):
                phrase = f"Несостоявшееся действие «{stored[target]['surface']}»."
                answers[phrase.casefold()] = phrase
                continue
            span = [target]
            for node in span:
                span.extend(j for j in surface_children[node] if stored[j]['role'] != 'clause_relative')
            span = [j for j in span if not stored[j].get('implicit')]
            first, last = min(span), max(span)
            included = set(span)
            if any(j not in included and stored[j]['role'] != 'punctuation' for j in range(first, last + 1)):
                continue
            phrase = source[stored[first]['start']:stored[last]['end']]
            answers[phrase.casefold()] = phrase
        else:
            head = mapping[focus]
            if stored[head].get('rule') == 'CL.NOMREF':
                head = stored[head]['antecedent']
            if rows[focus].get('quantity_kind') == 'query':
                head = _quantity_answer_head(rows[focus], stored, surface_children, head)
                if head is None:
                    continue
            parts = (_descendants(surface_children, [head]) if adjuncts.question(rows[focus])
                     else _nominal_parts(stored, surface_children, head))
            parts = set(parts)
            elaborations = [j for j in surface_children[head] if stored[j].get('rule') == 'CONTENT.NOMINAL']
            if elaborations:
                parts.update(_descendants(surface_children, [head]))
            if stored[head].get('correlative_quantity') and stored[head]['role'] == 'numeral':
                parts.add(stored[head]['head'])
            included_clauses = {clause for anchor in parts for clause in restrictions.get(anchor, ())}
            parts.update(_descendants(surface_children, included_clauses))
            if stored[head].get('scope') == 'focus_exclusive' and stored[head]['assertion_status'] == 'asserted':
                missing.difference_update(j for j in surface_children[head] if stored[j]['rule'] == 'F.NP')
            if missing and not missing.issubset(parts):
                continue
            answer = (_restricted_answer(stored, parts, source) if included_clauses or elaborations else
                      _nominal_answer(stored, parts, source))
            if answer:
                identity, phrase = answer
                if (rows[focus].get('quantity_kind') == 'query' and rows[focus]['role'] == 'object'
                        and stored[head]['role'] == 'numeral'):
                    from .distribution_questions import measure_unit

                    unit = stored[stored[head]['head']]
                    if measure_unit(rows[root]['lemma'], unit['lemma']):
                        identity = (unit['lemma'], identity)
                        phrase += ' ' + unit['surface']
                answers[identity] = phrase
    return answers


def _compatible(rows, i, stored, focus, root, variable_subject):
    row = rows[i]
    if focus and stored.get('rule') in ('CONTENT.EXPL', 'CONTENT.ANCHOR'):
        return (row['role'] == 'object' and row['lemma'] == 'что' and
                (stored['rule'] == 'CONTENT.ANCHOR' or stored['role'] == 'clause_complement'))
    if focus and stored.get('rule') in ('UTT.QUOTE', 'CL.POLAR'):
        return row['role'] == 'object' and row['lemma'] == 'что' and 'quotation' not in row
    if ('quotation' in row) != ('quotation' in stored):
        return False
    if row.get('scope') != stored.get('scope') or row['assertion_status'] != stored['assertion_status']:
        return False
    if not focus:
        if row.get('event_view') != stored.get('event_view'):
            return False
        if (row.get('antecedent') is None) != (stored.get('antecedent') is None):
            return False
    if row['role'] != stored['role'] and not (root and (stored['role'] == 'clause_relative' or stored.get('rule') == 'GAP')):
        if not focus or row['head'] is None:
            return False
        if (row['role'], stored['role']) == ('oblique', 'instrument'):
            if row.get('case') != 'ablt' or stored.get('case') != 'ablt':
                return False
        elif (row['role'], stored['role']) == ('object', 'recipient'):
            frame = FRAMES.get(rows[row['head']]['lemma'])
            if frame is None or 'accs' not in frame.recipient_cases or stored.get('case') != 'accs':
                return False
        else:
            return False
    if row.get('quantity_kind'):
        return _quantity_matches(row, stored, focus)
    if not focus:
        left, right = row.get('morphology') or {}, stored.get('morphology') or {}
        if left.get('pos') in ('PRTF', 'PRTS') or right.get('pos') in ('PRTF', 'PRTS'):
            if (row['lemma'] != stored['lemma'] or
                    any(left.get(k) != right.get(k) for k in ('pos', 'voice', 'aspect', 'tense', 'mood', 'transitivity'))):
                return False
            if 'PART.SUBSTANTIVE' in (row.get('rule'), stored.get('rule')):
                return (row.get('rule') == stored.get('rule') and _case(row) == _case(stored)
                        and all(left.get(k) == right.get(k) for k in ('number', 'gender')))
            if left.get('pos') == 'PRTF' or variable_subject:
                return True
            return all(left.get(k) == right.get(k) for k in ('number', 'gender'))
        if row.get('count_agreement') and stored.get('count_agreement'):
            return row['lemma'] == stored['lemma']
        if not row.get('counted') and stored.get('count_number'):
            return (row['lemma'] == stored['lemma'] and _case(row) == _case(stored) and
                    left.get('number') == stored['count_number'])
        if row.get('counted') and stored.get('counted'):
            right = (stored.get('morphology') or {}).get('number')
            if row['counted'] == 'query' and stored['counted'] == 'fraction' and right == 'plur':
                return False
            if row['counted'] in ('fraction', 'ordinal') and stored['counted'] == row['counted']:
                left = (row.get('morphology') or {}).get('number')
                if not left or left != right:
                    return False
            return row['lemma'] == stored['lemma'] and _case(row) == _case(stored)
        if row['lemma'] in PERSONAL or stored['lemma'] in PERSONAL:
            if 'quotation' in row:
                return row['lemma'] == stored['lemma'] and _case(row) == _case(stored)
            return (row['lemma'] in PERSONAL and stored['lemma'] in PERSONAL and _case(row) == _case(stored) and
                    row.get('participant_ref') is not None and row['participant_ref'] == stored.get('participant_ref') and
                    (row['lemma'] == stored['lemma'] or {row['lemma'], stored['lemma']} == {'я', 'ты'}))
        if left and right and row['lemma'] == stored['lemma'] and left.get('mood') and right.get('mood'):
            categories = ('tense', 'aspect', 'mood', 'voice', 'transitivity')
            if any(left.get(k) != right.get(k) for k in categories):
                return False
            if variable_subject or (row.get('collective_agreement') and stored.get('collective_agreement')):
                return True
            if all(left.get(k) == right.get(k) for k in ('number', 'gender')):
                if left.get('person') == right.get('person') or {left.get('person'), right.get('person')} == {'1per', '2per'}:
                    return True
            return False
        actual = (stored.get('recovery') or {}).get('corrected', stored['surface'])
        wanted = (row.get('recovery') or {}).get('corrected', row['surface'])
        return row['lemma'] == stored['lemma'] and wanted.casefold() == actual.casefold()
    if row['role'] == 'possessive' and row['lemma'] == 'чей':
        return stored['role'] == 'possessive' and stored.get('antecedent') is not None
    if stored.get('event_view'):
        return row['lemma'] == 'что'
    cases = {tag.case for lemma, tag in known_forms(row['surface']) if lemma == row['lemma'] and tag.POS == 'NPRO'}
    actual_case = _case(stored)
    if stored['lemma'] in PERSONAL:
        return row['lemma'] == 'кто' and stored.get('participant_ref') is not None and actual_case in cases
    animacy = 'anim' if row['lemma'] == 'кто' else 'inan'
    if stored.get('member_animacy'):
        return actual_case in cases and stored['member_animacy'] == animacy
    if stored.get('rule') == 'CL.NOMREF':
        return actual_case in cases and stored.get('relative_animacy') == animacy
    if stored.get('quantity_kind'):
        form_animacy = (stored.get('morphology') or {}).get('animacy')
        if not form_animacy and stored['quantity_kind'] == 'collective' and stored['role'] == 'subject':
            form_animacy = 'anim'
        return actual_case in cases and form_animacy == animacy
    surface = (stored.get('recovery') or {}).get('corrected', stored['surface'])
    if stored.get('counted'):
        if stored.get('rule') == 'GAP.NOUN':
            return actual_case in cases and stored['morphology']['animacy'] == animacy
        return actual_case in cases and any(lemma == stored['lemma'] and tag.POS == 'NOUN' and tag.animacy == animacy
                                            for lemma, tag in known_forms(surface))
    return any(lemma == stored['lemma'] and tag.POS in ('NOUN', 'NPRO') and tag.case in cases and
               (not actual_case or tag.case == actual_case) and tag.animacy == animacy
               for lemma, tag in known_forms(surface))


def _group_reading(store, group, rows, root, stored, observed, target, question, budget):
    from .probe import Probe

    member, anchor = target
    source = group.meta['verbatim']
    if (stored[observed]['assertion_status'] != 'asserted' or stored[observed].get('scope')
            or not _compatible(rows, root, stored[observed], False, True, True)):
        return None
    children = [[] for _ in stored]
    for j, row in enumerate(stored):
        if row.get('head') is not None:
            children[row['head']].append(j)
    parts = _descendants(children, [anchor])
    if not any(stored[i]['role'] == 'nominal_conjunct' for i in parts):
        return None
    for i in parts:
        row = stored[i]
        if i >= len(group.members) or row['head'] is None or row['head'] >= len(group.members):
            return None
        if store.find_link('grammar.' + row['role'], group.members[i].uid, group.members[row['head']].uid) is None:
            return None
        if row['role'] == 'coordinator':
            if row.get('scope') != 'addition' and (row['lemma'] != 'и' or row.get('scope')):
                return None
        elif row.get('scope') or row['role'] not in ('subject', 'nominal_conjunct', 'coordinator_part', 'punctuation'):
            return None
    if not _extraction(rows, stored, observed, source, None, budget, subject_member=target):
        return None
    phrase = _nominal_answer(stored, _nominal_parts(stored, children, anchor), source)
    if not phrase:
        return None
    individual = stored[member]['surface']
    wording = (f'Следует ли из текста ответ «да» на вопрос «{" ".join(question.split())}»? '
               f'Если следует, выберите «{individual}». Если сказанное верно только для группы, выберите группу.')
    return Probe(wording, (individual, phrase[1]), source)


def _answer(view, rows, focus, budget, result, participants, group_readings):
    rows = _query_rows(rows, participants, budget)
    if rows is None:
        return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
    from . import distribution_reading

    proofs = {}
    answers = {}
    for identity, text, ref, support in distribution_reading.answers(view, rows, focus, participants, budget):
        proofs[(text, ref)] = support
        answers.setdefault(identity, (text, ref))
    root = _root(rows)
    lemma = rows[root]['lemma']
    subjects = [row for row in rows if row['role'] == 'subject' and row['head'] == root]
    anchored = ((focus is None or rows[focus].get('quantity_kind') == 'query')
                and len(subjects) == 1 and (subjects[0].get('morphology') or {}).get('pos') == 'NOUN' and subjects[0]['lemma'] not in PERSONAL
                and not subjects[0].get('implicit') and (rows[root].get('morphology') or {}).get('pos') == 'VERB'
                and all(row['role'] in ('predicate', 'subject', 'punctuation', 'object', 'numeral') for row in rows))
    candidates = (_subject_lookup(view, subjects[0]['lemma'], lemma) if anchored else
                  ((group, stored, observed, None) for group, stored, observed in _lookup(view, lemma)))
    for group, stored, observed, target in candidates:
        stored = _query_rows(stored, _participants(group.meta.get('source')), budget)
        if stored is None:
            group_readings.clear()
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        surfaces = _extraction(rows, stored, observed, group.meta['verbatim'], focus, budget)
        if surfaces is None:
            group_readings.clear()
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        if focus is None and target is not None and not surfaces:
            probe = _group_reading(view.store, group, rows, root, stored, observed, target, result.source, budget)
            if probe:
                group_readings.setdefault(probe, group.uid)
        for identity, surface in surfaces.items():
            answers.setdefault(identity, (surface, group.uid))
    if len(answers) == 1:
        surface, ref = next(iter(answers.values()))
        return GrammarReply('ANSWER', surface, ref, result, proofs.get((surface, ref), ()))
    return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)


def submit(core, text, choose=None, *, source='user', speaker_ref=None, addressee_ref=None, journal=None, budget=256):
    words = TOKEN.findall(text)
    if not words:
        return GrammarReply('UNRESOLVED', 'Пустой ввод.')
    marked_question = words[-1] == '?'
    query_hint = marked_question or _question_word(words[0])
    initial_arg = _argument_question(words[0])
    initial_quantity = any(lemma == 'сколько' and tag.POS == 'NUMR' for lemma, tag in known_forms(words[0]))
    if initial_arg or initial_quantity:
        def accept(tree):
            first = tree[0]
            return (first.role == 'clause_marker' or first.quantity_kind == 'query' or
                    first.role == 'adverb' and first.lemma == 'сколько' or
                    first.role in ARGUMENTS and first.lemma in ('кто', 'что'))
    else:
        accept = None
    result = analyze(text, choose, budget=budget, accept_tree=accept)
    if len(result.analyses) != 1 or result.status != 'PARSED_FRAGMENT':
        if query_hint and result.status != 'AMBIGUOUS':
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        return GrammarReply(result.status, 'Разбор не завершён. ' + result.reason, analysis=result)
    if result.reason == 'NOMINAL_FRAGMENT':
        return GrammarReply('PARSED_FRAGMENT', 'Распознана именная группа с уточнением.', analysis=result)
    participants = _participants(source, speaker_ref, addressee_ref)
    rows = _rows(result, participants)
    fixed_expressions = {row['head'] for row in rows if row['role'] == 'fixed'}
    variables = [i for i, row in enumerate(rows) if i not in fixed_expressions and row['role'] != 'fixed' and
                 'quotation' not in row and row.get('antecedent') is None and row['rule'] not in ('CL.WH', 'CL.SPATIAL.WH', 'CL.SPATIAL.FREE', 'NEG.PRON.ARG') and
                 row['role'] not in ('clause_marker', 'coordinator', 'preposition', 'case', 'prep_part') and
                 _question_word(row['surface'], row['lemma'])]
    if marked_question or variables or any(row['rule'] == 'UTT.POLAR' and 'quotation' not in row for row in rows):
        if len(variables) > 1 or any(not (adjuncts.question(rows[i]) or rows[i]['role'] == 'possessive' and rows[i]['lemma'] == 'чей'
                                          or rows[i]['rule'] == 'NEG.EXIST.OWNER' and rows[i]['lemma'] == 'кто' or rows[i]['role'] in ARGUMENTS and rows[i]['lemma'] in ('кто', 'что') or
                                          rows[i].get('quantity_kind') == 'query' and rows[i]['role'] in ARGUMENTS | {'numeral'})
                                     for i in variables):
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        group_readings = {}
        with _access(core, _adapter(core, journal)) as view:
            reply = _answer(view, rows, next(iter(variables), None), budget, result, participants, group_readings)
        if reply.status == 'UNKNOWN' and group_readings:
            asked = []
            if choose is not None:
                for probe, ref in group_readings.items():
                    if len(asked) >= budget:
                        break
                    asked.append(probe)
                    try:
                        choice = choose(probe)
                    except OSError:
                        break
                    if isinstance(choice, Mapping):
                        choice = probe.response_choice(choice)
                    if isinstance(choice, str) and choice.strip().casefold() == probe.options[0].casefold():
                        result = replace(result, probes=(*result.probes, *asked))
                        return GrammarReply('ANSWER', 'Да.', ref, result)
            result = replace(result, probes=(*result.probes, *asked))
            probe, ref = next(iter(group_readings.items()))
            return GrammarReply('EVIDENCE', f'В памяти записано: «{probe.context}»', ref, result)
        return reply
    root = rows[_root(rows)]
    if (root['rule'] == 'V.IMP' or (root.get('morphology') or {}).get('mood') == 'impr'
            or 'directive' in (root.get('scope') or '').split('_')):
        prohibition = 'negated' in (root.get('scope') or '').split('_')
        act = 'Распознан запрет на действие' if prohibition else 'Распознано побуждение к действию'
        return GrammarReply('DIRECTIVE', f"{act} «{root['lemma']}».", analysis=result)
    reason = violation(result.tokens, result.analyses[0])
    if reason:
        rejected = Result(result.source, 'UNRESOLVED', reason, result.tokens, probes=result.probes, steps=result.steps)
        return GrammarReply('UNRESOLVED', 'Разбор не завершён. ' + reason, analysis=rejected)
    from . import distribution_selection

    distributions, result = distribution_selection.select(rows, result, choose, budget)
    if result.status != 'PARSED_FRAGMENT':
        return GrammarReply(result.status, 'Не установлена область распределения.', analysis=result)
    with _access(core, _adapter(core, journal), write=True) as draft:
        reference = _remember(draft, result, rows, source, distributions)
    return GrammarReply('STORED', 'Наблюдение записано.', reference, result)
