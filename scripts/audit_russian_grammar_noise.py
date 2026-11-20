import argparse
import hashlib
import json
import signal
from pathlib import Path

from accept_russian_grammar_second_ten import read_graph, sample
from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit
from ah.russian_grammar.prepositions import TOKEN


EVIDENCE = Path(__file__).resolve().parents[1] / 'docs/evidence/russian_grammar_second_ten'
TYPOS = {
    'test-s12': ('оценкам', 'оценкм'),
    'test-s13': ('предоставлению', 'предоствалению'),
    'test-s14': ('КОАТУУ', 'КОАТУ'),
    'test-s15': ('апреля', 'апрлея'),
    'test-s16': ('ремонт', 'ремнот'),
    'test-s17': ('посылал', 'посыллал'),
    'test-s18': ('глазами', 'глазми'),
    'test-s19': ('малыш', 'малшы'),
    'test-s20': ('получила', 'получла'),
    'test-s21': ('форты', 'фроты'),
}
PUNCTUATION = frozenset({',', '.', ':', ';', '(', ')', '--', '—', '–', '!', '?', '«', '»'})
LINKS = ('head', 'controller', 'antecedent', 'ellipsis_source', 'coord_head', 'shared_agent', 'shared_object')
FIELDS = ('lemma', 'role', 'assertion_status', 'assertion_context', 'scope', 'quantity', 'quantity_kind',
          'quantity_modifier', 'case', 'event_view', 'implicit_subject')


def variants(identity, text):
    yield 'original', text
    plain = TOKEN.sub(lambda m: ' ' if m[0] in PUNCTUATION else m[0], text)
    plain = ' '.join(plain.split())
    yield 'no_punctuation', plain
    old, new = TYPOS[identity]
    if text.count(old) != 1:
        raise ValueError((identity, old))
    yield 'typo', text.replace(old, new)
    yield 'no_punctuation_and_typo', plain.replace(old, new)
    if identity == 'test-s12':
        for left, right, label in [(',', '', 'left_comma'), ('', ',', 'right_comma'), ('', '', 'no_pair')]:
            yield label, text.replace('которому, по оценкам учёных,', f'которому{left} по оценкам учёных{right}')


def projection(core, uid, text):
    group = core.store.get_element(Domain.H, uid)
    if group.meta['verbatim'] != text:
        raise ValueError('Verbatim text changed')
    rows = [core.store.get_element(Domain.H, m.uid).meta for m in group.members]
    indices = [i for i, row in enumerate(rows) if row['surface'] not in PUNCTUATION]
    normalized = {i: j for j, i in enumerate(indices)}
    edges = {(l.source, l.target, l.relation_id) for l in core.store.links()}
    records = []
    for i in indices:
        row = rows[i]
        values = {f: row[f] for f in FIELDS if row.get(f) is not None}
        for key in LINKS:
            target = row.get(key)
            if target is None:
                continue
            relation = 'grammar.' + (row['role'] if key == 'head' else key)
            if (group.members[i], group.members[target], relation) not in edges:
                raise ValueError(f'Missing graph edge at {i} {key}')
            values[key] = normalized[target] if target in normalized else f'punctuation {target}'
        records.append(values)
    return records


def digest(graph):
    wire = json.dumps(graph, ensure_ascii=False, separators=(',', ':'), sort_keys=True)
    return hashlib.sha256(wire.encode()).hexdigest()


def run(identity, kind, text, gold, teacher, seconds):
    core = AHCore()
    answers = {}
    for item in teacher['calls']:
        answers.setdefault(item['question'], set()).add(item['answer'])
    rows = teacher['rows']
    old, new = TYPOS[identity]
    open_questions = []
    probes = 0

    def choose(p):
        nonlocal probes
        probes += 1
        if kind == 'original':
            prior = teacher['calls'][probes - 1] if probes <= len(teacher['calls']) else {}
            if prior.get('question') == p.question and prior.get('options') == list(p.options):
                return prior['answer']
            open_questions.append({'question': p.question, 'options': list(p.options)})
            return '?'
        question = p.question.replace(new, old) if 'typo' in kind else p.question
        if identity == 'test-s12' and question == 'Какие слова здесь образуют отдельную группу меры?':
            choices = {'14 метров в охвате'}
        elif identity == 'test-s19' and question == 'Какие слова продолжают перечисление после «папе»?':
            choices = {'к кораблю'}
        elif identity == 'test-s19' and question in (
                'Which word does the phrase «к папе» depend on?',
                'Which word does the phrase «к кораблю» depend on?',
                'Which word does the phrase «к папе к кораблю» depend on?'):
            choices = {'идти'}
        elif p.options and p.question == f'Какое написание передаёт слово «{p.options[0]}» в этом предложении?':
            intended = old if 'typo' in kind and p.options[0] == new else p.options[0]
            if intended in p.options and not (identity == 'test-s14' and intended == old):
                return intended
            choices = set()
        else:
            choices = answers.get(question, set())
            if not choices and question.startswith('Which word does the phrase «') and question.endswith('» depend on?'):
                phrase = question.removeprefix('Which word does the phrase «').removesuffix('» depend on?')
                words = [m[0] for m in TOKEN.finditer(phrase)]
                starts = [i for i, row in enumerate(rows) if row[1] == 'preposition' and row[2] is not None
                          and [word[0] for word in rows[i:i + len(words)]] == words]
                choices = {rows[rows[i][2]][0] for i in starts}
            if not choices and question.startswith('Какое сочетание передаёт оговорку к самому сообщению о действии «'):
                head = question.rsplit('«', 1)[-1].removesuffix('»?')
                hits = [r for r in rows if r[0] == head]
                if len(hits) == 1 and hits[0][4] == 'asserted':
                    choices = {'нет такого сочетания'}
        matches = [o for o in p.options if (o.replace(new, old) if 'typo' in kind else o) in choices]
        if len(matches) == 1:
            return matches[0]
        open_questions.append({'question': p.question, 'options': list(p.options)})
        return '?'

    record = {'id': identity, 'variant': kind, 'text': text}
    graph = None
    signal.setitimer(signal.ITIMER_PROF, seconds)
    try:
        reply = submit(core, text, choose)
    except TimeoutError:
        reply = None
    finally:
        signal.setitimer(signal.ITIMER_PROF, 0)
    if reply is None:
        record['status'] = 'TIME_LIMIT'
    else:
        record.update(status=reply.status, reason=reply.analysis.reason)
    if record['status'] == 'STORED':
        graph = projection(core, reply.observation_ref, text)
        if kind == 'original':
            checked = read_graph(core, reply, text, gold, identity)
            record['matches_original_acceptance'] = not checked['errors'] and not checked.get('differences')
    elif core.store.links() or any(core.store.elements(domain) for domain in Domain):
        raise ValueError('Incomplete submit changed memory')
    record['probes'] = probes
    if kind == 'original':
        record['matches_original_probes'] = not open_questions and probes == len(teacher['calls'])
    if open_questions:
        record['unanswered'] = open_questions
    return record, graph


def expire(*_):
    raise TimeoutError


def regressions(results, previous):
    failed = []
    for row in results:
        key = (row['id'], row['variant'])
        old = previous[key]
        if row['variant'] == 'original' and not (
                row.get('matches_original_probes') and row.get('matches_original_acceptance')):
            failed.append((*key, 'original acceptance or probes changed'))
        elif old.get('matches_reference') and not row.get('matches_reference'):
            failed.append((*key, 'lost a previously matching graph'))
        elif row.get('matches_reference') is False and row['graph_sha256'] != old.get('graph_sha256'):
            failed.append((*key, 'stored a new divergent graph'))
    return failed


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--baseline', type=Path)
    parser.add_argument('--expect', type=Path)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    signal.signal(signal.SIGPROF, expire)
    teachers = {r['id']: r for r in json.loads((EVIDENCE / 'results.json').read_text(encoding='utf-8'))['cases']
                if r['mode'] == 'teacher'}
    previous = {}
    if args.baseline:
        previous_data = json.loads(args.baseline.read_text(encoding='utf-8'))
        if previous_data['cpu_seconds_per_case'] != args.seconds:
            raise ValueError('Use the same time limit for the baseline and the revision')
        previous = {(r['id'], r['variant']): r for r in previous_data['cases']}
    expected = previous
    if args.expect:
        if not previous:
            parser.error('--expect requires an original graph from --baseline')
        expectation = json.loads(args.expect.read_text(encoding='utf8'))
        if expectation['cpu_seconds_per_case'] != args.seconds:
            parser.error('Use the same time limit for the expected results and the revision')
        expected = {(r['id'], r['variant']): r for r in expectation['cases']}
    results = []
    for identity, source, gold in sample(args.corpus):
        reference = previous.get((identity, 'original'), {}).get('reference')
        for kind, text in variants(identity, source):
            result, graph = run(identity, kind, text, gold, teachers[identity], args.seconds)
            if kind == 'original' and not args.baseline:
                if not (result.get('matches_original_acceptance') and result['matches_original_probes']):
                    raise ValueError(f'{identity}: could not reproduce reference')
                result['reference'] = reference = graph
            if graph is not None:
                result['matches_reference'] = graph == reference
                result['graph_sha256'] = digest(graph)
                if graph != reference:
                    result['differences'] = [
                        {'token': i + 1, 'field': key, 'expected': old.get(key), 'actual': actual.get(key)}
                        for i, (actual, old) in enumerate(zip(graph, reference))
                        for key in sorted(set(old) | set(actual)) if old.get(key) != actual.get(key)
                    ]
                    result['length_delta'] = len(graph) - len(reference)
            if previous:
                old = previous[identity, kind]
                result['baseline'] = {k: old[k] for k in ('status', 'reason', 'probes', 'matches_reference') if k in old}
            results.append(result)
            print(identity, kind, result['status'], result.get('matches_reference'), flush=True)
    args.output.write_text(json.dumps({'cpu_seconds_per_case': args.seconds, 'cases': results},
                                      ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    if expected:
        failures = regressions(results, expected)
        if failures:
            raise SystemExit('\n'.join(' '.join(failure) for failure in failures))



if __name__ == '__main__':
    main()
