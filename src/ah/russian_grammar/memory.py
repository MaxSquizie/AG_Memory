from contextlib import contextmanager
from dataclasses import asdict, dataclass
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
UNKNOWN = 'Неизвестно.'
ARGUMENTS = {'subject', 'comparison_standard', 'object', 'recipient', 'experiencer', 'beneficiary', 'stimulus', 'instrument', 'oblique', 'agent'}
AMOUNTS = {'cardinal', 'collective', 'both', 'fraction', 'range', 'indefinite'}
NUMBER_PARTS = {'numeral_part', 'quantity_modifier'}
PERSONAL = {'я': 'speaker', 'ты': 'addressee', 'мы': 'speaker_group', 'вы': 'addressee_group'}
INTERROGATIVES = frozenset('кто что какой который чей сколько где куда откуда когда почему зачем как каков'.split())


@dataclass(frozen=True)
class GrammarReply:
    status: str
    text: str
    observation_ref: str | None = None
    analysis: Result | None = None


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
        if row['role'] != 'clause_marker' or not row.get('scope'):
            continue
        host = row['head']
        contexts[host] = row['scope']
        qualification = {'condition': 'conditional', 'alternative': 'alternative', 'adverbial': 'adverbial'}.get(row['scope'])
        if qualification and rows[host]['head'] is not None:
            qualifications[rows[host]['head']] = qualification
    pending = [(root, None, 'asserted')]
    while pending:
        i, enclosing, governing_status = pending.pop()
        row = rows[i]
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
            if role in ('clause_adverbial', 'clause_complement', 'infinitive'):
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


def _remember(core, result, rows, source):
    root = rows[_root(rows)]
    projected = set(homogeneous.projection_members(rows, _root(rows))) - {_root(rows)}
    members = []
    for i, row in enumerate(rows):
        props = {}
        parts = lexical_parts.metadata(row['surface'], row['start'], row['lemma'])
        if parts:
            row['lexical_parts'] = list(parts)
        if (row['role'] == 'clause_relative' or row['rule'] == 'GAP') and row['assertion_status'] == 'asserted':
            key = GAP_KEY if row['rule'] == 'GAP' else RELATIVE_KEY
            props[key] = Property(key, row['lemma'], 'str')
        if i in projected and row['assertion_status'] == 'asserted':
            props[CONJUNCT_KEY] = Property(CONJUNCT_KEY, row['lemma'], 'str')
        members.append(core.ref(core.add_entity(Domain.H, properties=props, meta=row).uid))
    for i, row in enumerate(rows):
        for key in ('head', 'controller', 'antecedent', 'ellipsis_source', 'coord_head', 'shared_agent', 'shared_object'):
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
    return observation.uid


def _lookup(core, lemma):
    def rows_of(group):
        rows = tuple(core.store.get_element(Domain.H, member.uid).meta for member in group.members)
        for member, row in zip(group.members, rows):
            if not _correlative_reference(row):
                continue
            anchor = row.get('antecedent')
            if (anchor is None or not 0 <= anchor < len(rows) or
                    core.store.find_link('grammar.antecedent', member.uid, group.members[anchor].uid) is None):
                return None
        return rows

    for ref in core.store.find_elements_with_property(ROOT_KEY, lemma):
        group = core.store.get_element(Domain.H, ref.uid)
        rows = rows_of(group)
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
            rows = rows_of(group)
            if rows is None:
                continue
            members = homogeneous.projection_members(rows, _root(rows))
            target = group.members.index(ref)
            if target in members and (projection := homogeneous.project(rows, members, target)):
                yield group, *projection
    for key in (RELATIVE_KEY, GAP_KEY):
        for ref in core.store.find_elements_with_property(key, lemma):
            for group in core.store.groups_containing(ref.uid):
                if group.meta.get('kind') == 'russian_grammar.observation':
                    rows = rows_of(group)
                    if rows is not None:
                        yield group, rows, group.members.index(ref)


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
    return key is not None and key[0] in AMOUNTS and (not qualifier or qualifier == key[2])


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
            elif (stored[child].get('rule') == 'NP.DET' or role in NUMBER_PARTS or role in ('name_part', 'nominal_conjunct', 'coordinator', 'numeral') or
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
        if word is None:
            return None
        words.append(word)
        if row.get('quantity_kind') and row['role'] not in NUMBER_PARTS:
            identity.append(_quantity_key(row) or word.casefold())
        elif row['role'] not in NUMBER_PARTS:
            identity.append(word.casefold())
    phrase = ' '.join(words)
    if any(stored[j]['role'] in ('participle', 'genitive_modifier') for j in parts):
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
    if rows[root].get('rule') == 'NEG.EXIST':
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
    return (row.get('rule') == 'CL.SPATIAL.REF' or
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


def _extraction(rows, stored, observed, source, focus, budget):
    root = _root(rows)
    if any(row.get('implicit_subject') == 'unresolved' and (focus is None or i != root) for i, row in enumerate(rows)):
        return {}
    scoped_question = focus is not None and bool(rows[root].get('scope')) and rows[root]['rule'] != 'NEG.EXIST'
    if scoped_question and not any(row['role'] == 'clause_marker' and row.get('scope') in ('condition', 'adverbial')
                                   for row in rows):
        return {}
    children = [[] for _ in rows]
    for i, row in enumerate(rows):
        if row['head'] is not None and row['role'] != 'punctuation' and row['role'] not in NUMBER_PARTS and row.get('scope') != 'ordering':
            children[row['head']].append(i)
    surface_children = [[] for _ in stored]
    for j, row in enumerate(stored):
        if row['head'] is not None and row['role'] != 'punctuation':
            surface_children[row['head']].append(j)
    children_found = [[j for j in group if stored[j]['role'] not in NUMBER_PARTS and stored[j].get('scope') != 'ordering']
                      for group in surface_children]
    if not scoped_question and not any(row['role'] == 'clause_relative' for row in rows):
        children_found = [[j for j in group if stored[j]['role'] != 'clause_relative'] for group in children_found]
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
            included_clauses = {clause for anchor in parts for clause in restrictions.get(anchor, ())}
            parts.update(_descendants(surface_children, included_clauses))
            if stored[head].get('scope') == 'focus_exclusive' and stored[head]['assertion_status'] == 'asserted':
                missing.difference_update(j for j in surface_children[head] if stored[j]['rule'] == 'F.NP')
            if missing and not missing.issubset(parts):
                continue
            answer = (_restricted_answer(stored, parts, source) if included_clauses else
                      _nominal_answer(stored, parts, source))
            if answer:
                identity, phrase = answer
                answers[identity] = phrase
    return answers


def _compatible(rows, i, stored, focus, root, variable_subject):
    row = rows[i]
    if focus and stored.get('rule') == 'UTT.QUOTE':
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
            if variable_subject:
                return True
            if all(left.get(k) == right.get(k) for k in ('number', 'gender')):
                if left.get('person') == right.get('person') or {left.get('person'), right.get('person')} == {'1per', '2per'}:
                    return True
            return False
        actual = (stored.get('recovery') or {}).get('corrected', stored['surface'])
        wanted = (row.get('recovery') or {}).get('corrected', row['surface'])
        return row['lemma'] == stored['lemma'] and wanted.casefold() == actual.casefold()
    if stored.get('event_view'):
        return row['lemma'] == 'что'
    cases = {tag.case for lemma, tag in known_forms(row['surface']) if lemma == row['lemma'] and tag.POS == 'NPRO'}
    actual_case = _case(stored)
    if stored['lemma'] in PERSONAL:
        return row['lemma'] == 'кто' and stored.get('participant_ref') is not None and actual_case in cases
    animacy = 'anim' if row['lemma'] == 'кто' else 'inan'
    if stored.get('rule') == 'CL.NOMREF':
        return actual_case in cases and stored.get('relative_animacy') == animacy
    if stored.get('quantity_kind'):
        form_animacy = (stored.get('morphology') or {}).get('animacy')
        if not form_animacy and stored['quantity_kind'] == 'collective' and stored['role'] == 'subject':
            form_animacy = 'anim'
        return actual_case in cases and form_animacy == animacy
    surface = (stored.get('recovery') or {}).get('corrected', stored['surface'])
    if stored.get('counted'):
        return actual_case in cases and any(lemma == stored['lemma'] and tag.POS == 'NOUN' and tag.animacy == animacy
                                            for lemma, tag in known_forms(surface))
    return any(lemma == stored['lemma'] and tag.POS in ('NOUN', 'NPRO') and tag.case in cases and
               (not actual_case or tag.case == actual_case) and tag.animacy == animacy
               for lemma, tag in known_forms(surface))


def _answer(view, rows, focus, budget, result, participants):
    rows = _query_rows(rows, participants, budget)
    if rows is None:
        return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
    answers = {}
    lemma = rows[_root(rows)]['lemma']
    for group, stored, observed in _lookup(view, lemma):
        stored = _query_rows(stored, _participants(group.meta.get('source')), budget)
        if stored is None:
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        surfaces = _extraction(rows, stored, observed, group.meta['verbatim'], focus, budget)
        if surfaces is None:
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        for identity, surface in surfaces.items():
            answers.setdefault(identity, (surface, group.uid))
    if len(answers) == 1:
        surface, ref = next(iter(answers.values()))
        return GrammarReply('ANSWER', surface, ref, result)
    return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)


def submit(core, text, choose=None, *, source='user', speaker_ref=None, addressee_ref=None, journal=None, budget=256):
    words = TOKEN.findall(text)
    if not words:
        return GrammarReply('UNRESOLVED', 'Пустой ввод.')
    marked_question = words[-1] == '?'
    query_hint = marked_question or _question_word(words[0]) or any(w.casefold() == 'ли' for w in words)
    initial_arg = _argument_question(words[0])
    initial_quantity = any(lemma == 'сколько' and tag.POS == 'NUMR' for lemma, tag in known_forms(words[0]))
    if initial_arg or initial_quantity:
        def accept(tree):
            first = tree[0]
            return (first.role == 'clause_marker' or first.quantity_kind == 'query' or
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
                 'quotation' not in row and row.get('antecedent') is None and row['rule'] not in ('CL.WH', 'CL.SPATIAL.WH', 'CL.SPATIAL.FREE') and
                 row['role'] not in ('clause_marker', 'coordinator') and _question_word(row['surface'], row['lemma'])]
    if marked_question or variables or any(row['lemma'] == 'ли' and row['role'] == 'particle' and 'quotation' not in row for row in rows):
        if len(variables) > 1 or any(not (adjuncts.question(rows[i]) or rows[i]['rule'] == 'NEG.EXIST.OWNER' and rows[i]['lemma'] == 'кто' or rows[i]['role'] in ARGUMENTS and rows[i]['lemma'] in ('кто', 'что') or
                                          rows[i].get('quantity_kind') == 'query' and rows[i]['role'] in ARGUMENTS | {'numeral'})
                                     for i in variables):
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        with _access(core, _adapter(core, journal)) as view:
            return _answer(view, rows, next(iter(variables), None), budget, result, participants)
    root = rows[_root(rows)]
    if root['rule'] == 'V.IMP' or (root.get('morphology') or {}).get('mood') == 'impr':
        prohibition = 'negated' in (root.get('scope') or '').split('_')
        act = 'Распознан запрет на действие' if prohibition else 'Распознано побуждение к действию'
        return GrammarReply('DIRECTIVE', f"{act} «{root['lemma']}».", analysis=result)
    reason = violation(result.tokens, result.analyses[0])
    if reason:
        rejected = Result(result.source, 'UNRESOLVED', reason, result.tokens, probes=result.probes, steps=result.steps)
        return GrammarReply('UNRESOLVED', 'Разбор не завершён. ' + reason, analysis=rejected)
    with _access(core, _adapter(core, journal), write=True) as draft:
        reference = _remember(draft, result, rows, source)
    return GrammarReply('STORED', 'Наблюдение записано.', reference, result)
