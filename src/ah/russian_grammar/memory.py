from contextlib import contextmanager
from dataclasses import asdict, dataclass
from uuid import uuid4

from ah.model import Domain, Property

from .infinitives import FRAMES
from .parser import Result, analyze
from .prepositions import TOKEN
from .rules import known_forms


ROOT_KEY = 'russian_grammar.root'
UNKNOWN = 'Неизвестно.'
ARGUMENTS = {'subject', 'object', 'recipient', 'experiencer'}
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


def _rows(result):
    rows = tuple({**asdict(token), **asdict(link)} for token, link in zip(result.tokens, result.analyses[0]))
    children = [[] for _ in rows]
    root = _root(rows)
    for i, row in enumerate(rows):
        if row['head'] is not None:
            children[row['head']].append(i)
    contexts = {}
    qualifications = {}
    for i, row in enumerate(rows):
        if row['role'] != 'clause_marker' or not row.get('scope'):
            continue
        host = row['head']
        contexts[host] = row['scope']
        if row['scope'] in ('condition', 'alternative') and rows[host]['head'] is not None:
            qualifications[rows[host]['head']] = 'conditional' if row['scope'] == 'condition' else 'alternative'
    pending = [(root, None, 'asserted')]
    while pending:
        i, enclosing, governing_status = pending.pop()
        row = rows[i]
        scope = row.get('scope') or ''
        category, _, polarity = scope.partition('_')
        if category in ('negated', 'averted'):
            category, polarity = '', category
        role = row['role']
        boundary = contexts.get(i)
        if role in ('predicate', 'clause_conjunct', 'clause_adverbial', 'clause_complement', 'converb', 'infinitive'):
            boundary = boundary or category
            if role in ('clause_adverbial', 'clause_complement', 'infinitive'):
                boundary = boundary or 'embedded'
            enclosing = enclosing or boundary or qualifications.get(i) or None
            status = enclosing or polarity or 'asserted'
        else:
            status = governing_status
        row['assertion_context'] = enclosing
        row['assertion_status'] = status
        pending.extend((j, enclosing, status) for j in children[i])
    return rows


def _remember(core, result, rows, source):
    root = rows[_root(rows)]
    members = tuple(core.ref(core.add_entity(Domain.H, meta=row).uid) for row in rows)
    for i, row in enumerate(rows):
        for key in ('head', 'controller'):
            if row.get(key) is not None:
                relation = 'grammar.' + (row['role'] if key == 'head' else 'controller')
                core.add_link(relation, members[i], members[row[key]], 1.0)
    observation = core.add_group(
        Domain.H, members, {ROOT_KEY: Property(ROOT_KEY, root['lemma'], 'str')},
        {'verbatim': result.source, 'source': source, 'kind': 'russian_grammar.observation',
         'root_status': root['assertion_status']},
    )
    return observation.uid


def _lookup(core, lemmas):
    for lemma in sorted(lemmas):
        for ref in core.store.find_elements_with_property(ROOT_KEY, lemma):
            group = core.store.get_element(Domain.H, ref.uid)
            yield group.uid, tuple(core.store.get_element(Domain.H, member.uid).meta for member in group.members)


def _question_word(word):
    return any(lemma in INTERROGATIVES or 'Ques' in tag for lemma, tag in known_forms(word))


def _argument_question(word):
    return any(lemma in ('кто', 'что') and tag.POS == 'NPRO' for lemma, tag in known_forms(word))


def _imperative(word):
    return any(tag.POS == 'VERB' and tag.mood == 'impr' for _, tag in known_forms(word))


def _extraction(rows, stored, focus, budget):
    root, observed = _root(rows), _root(stored)
    if focus is not None and rows[root].get('scope'):
        return set()
    children = [[] for _ in rows]
    for i, row in enumerate(rows):
        if row['head'] is not None and row['role'] != 'punctuation':
            children[row['head']].append(i)
    children_found = [[] for _ in stored]
    for j, row in enumerate(stored):
        if row['head'] is not None and row['role'] != 'punctuation':
            children_found[row['head']].append(j)
    if focus is None and sum(map(len, children)) != sum(map(len, children_found)):
        return set()
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
                if j in mapping.values() or not _compatible(rows, i, stored[j], i == focus):
                    continue
                following.append({**mapping, i: j})
                if len(following) > budget:
                    return None
        states = following
        if not states:
            break
    answers = set()
    for mapping in states:
        if any(rows[i].get('controller') is not None and
               mapping.get(rows[i]['controller']) != stored[j].get('controller') for i, j in mapping.items()):
            continue
        if focus is None:
            answers.add('Да.')
        else:
            head = mapping[focus]
            parts = [head, *(j for j in children_found[head] if stored[j]['role'] == 'name_part')]
            answers.add(' '.join(stored[j]['surface'] for j in sorted(parts)))
    return answers


def _compatible(rows, i, stored, focus):
    row = rows[i]
    if row.get('scope') != stored.get('scope') or row['assertion_status'] != stored['assertion_status']:
        return False
    if row['role'] != stored['role']:
        if not (focus and row['role'] == 'object' and stored['role'] == 'recipient' and row['head'] is not None):
            return False
        frame = FRAMES.get(rows[row['head']]['lemma'])
        if frame is None or 'accs' not in frame.recipient_cases or stored.get('case') != 'accs':
            return False
    if not focus:
        return row['lemma'] == stored['lemma'] and row['surface'].casefold() == stored['surface'].casefold()
    cases = {tag.case for lemma, tag in known_forms(row['surface']) if lemma == row['lemma'] and tag.POS == 'NPRO'}
    actual_case = stored.get('case') or {'subject': 'nomn', 'object': 'accs'}.get(stored['role'])
    animacy = 'anim' if row['lemma'] == 'кто' else 'inan'
    return any(lemma == stored['lemma'] and tag.POS in ('NOUN', 'NPRO') and tag.case in cases and
               (not actual_case or tag.case == actual_case) and tag.animacy == animacy
               for lemma, tag in known_forms(stored['surface']))


def _answer(view, rows, focus, budget, result):
    answers = {}
    lemma = rows[_root(rows)]['lemma']
    for ref, stored in _lookup(view, {lemma}):
        surfaces = _extraction(rows, stored, focus, budget)
        if surfaces is None:
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        for surface in surfaces:
            answers.setdefault(surface.casefold(), (surface, ref))
    if len(answers) == 1:
        surface, ref = next(iter(answers.values()))
        return GrammarReply('ANSWER', surface, ref, result)
    return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)


def submit(core, text, choose=None, *, source='user', journal=None, budget=256):
    words = TOKEN.findall(text)
    if not words:
        return GrammarReply('UNRESOLVED', 'Пустой ввод.')
    query = words[-1] == '?' or _question_word(words[0]) or any(w.casefold() == 'ли' for w in words)
    initial_arg = _argument_question(words[0])
    if initial_arg:
        def accept(tree):
            return tree[0].role in ARGUMENTS and tree[0].lemma in ('кто', 'что')
    else:
        accept = None
    result = analyze(text, choose, budget=budget, accept_tree=accept)
    if len(result.analyses) != 1 or result.status != 'PARSED_FRAGMENT':
        if query and result.status != 'AMBIGUOUS':
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        return GrammarReply(result.status, 'Разбор не завершён. ' + result.reason, analysis=result)
    rows = _rows(result)
    variables = [i for i, row in enumerate(rows) if _question_word(row['surface'])
                 and row['role'] not in ('clause_marker', 'coordinator')]
    if variables:
        query = True
    if query:
        if len(variables) > 1 or any(rows[i]['role'] not in ARGUMENTS or rows[i]['lemma'] not in ('кто', 'что')
                                     for i in variables):
            return GrammarReply('UNKNOWN', UNKNOWN, analysis=result)
        with _access(core, _adapter(core, journal)) as view:
            return _answer(view, rows, next(iter(variables), None), budget, result)
    root = rows[_root(rows)]
    if _imperative(root['surface']):
        return GrammarReply('UNRESOLVED', 'Форма допускает повелительное наклонение.', analysis=result)
    with _access(core, _adapter(core, journal), write=True) as draft:
        reference = _remember(draft, result, rows, source)
    return GrammarReply('STORED', 'Наблюдение записано.', reference, result)
