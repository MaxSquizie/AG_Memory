import argparse
from dataclasses import replace
from contextlib import contextmanager
import hashlib
import json
from pathlib import Path
import signal

from accept_russian_grammar_second_ten import DIGEST, mismatches
from audit_russian_grammar_noise import FIELDS, LINKS, digest
from measure_russian_grammar import sentences
from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import _rows, submit
from ah.russian_grammar.parser import _partition


def batch(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != DIGEST:
        raise ValueError('Unexpected Russian-GSD revision')
    return [case for case in sentences(path) if 22 <= int(case[0].split('-s')[1]) <= 31]


def bounds(text, rows):
    result = []
    end = 0
    for row in rows:
        start = text.index(row[1], end)
        if text[end:start].strip():
            raise ValueError(f'Unaligned text before {row[1]}')
        end = start + len(row[1])
        result.append((start, end))
    if text[end:].strip():
        raise ValueError('Unaligned tail')
    return result


def variants(text, rows):
    spans = bounds(text, rows)
    yield 'original', text, rows
    kept = [r for r in rows if r[3] != 'PUNCT']
    indices = {int(r[0]): i for i, r in enumerate(kept, 1)}
    plain = [r.copy() for r in kept]
    for row in plain:
        if row[1].endswith('.') and row[1][:-1].isalpha():
            row[1] = row[1][:-1]
        row[0] = str(indices[int(row[0])])
        row[6] = str(indices[int(row[6])] if int(row[6]) else 0)
    yield 'no_punctuation', ' '.join(r[1] for r in plain), plain
    priority = ('amod', 'nummod:gov', 'det', 'nmod', 'nsubj', 'case')
    sites = []
    for i, row in enumerate(rows):
        head = int(row[6]) - 1
        if row[7] in priority and head >= 0 and abs(i - head) == 1:
            sites.append((priority.index(row[7]), max(i, head)))
    index = min(sites)[1]
    cut = spans[index - 1][1]
    dirty = [r.copy() for r in rows]
    for i, row in enumerate(dirty):
        row[0] = str(i + 1 + int(i >= index))
        h = int(row[6])
        row[6] = str(h + int(h > index))
    dirty.insert(index, [str(index + 1), ',', ',', 'PUNCT', '_', '_', str(index), 'punct', '_', 'InjectedComma=Yes'])
    yield 'extra_comma', text[:cut] + ',' + text[cut:], dirty


def align(tokens, text, gold):
    aligned = [None] * len(tokens)
    targets = {}
    owners = {}
    for i, (row, (start, end)) in enumerate(zip(gold, bounds(text, gold))):
        inside = [j for j, token in enumerate(tokens) if start <= token.start and token.end <= end]
        if not inside:
            raise ValueError(f'No occurrence for {row[1]}')
        lexical = [j for j in inside if any(c.isalnum() for c in tokens[j].surface)]
        if row[3] != 'PUNCT' and len(inside) > 1 and len(lexical) != 1:
            raise ValueError(f'A lexical item has multiple parts: {row[1]}')
        main = lexical[0] if lexical else inside[0]
        targets[i + 1] = main
        for j in inside:
            record = row.copy()
            record[1] = tokens[j].surface
            aligned[j] = record
            if j == main:
                owners[j] = int(row[6])
            else:
                record[3], record[6], record[7] = 'PUNCT', str(main + 1), 'punct'
    if any(r is None for r in aligned):
        raise ValueError('A parser occurrence spans corpus words')
    for j, owner in owners.items():
        aligned[j][6] = str(targets[owner] + 1 if owner else 0)
    return aligned


def grammatical_errors(words, gold):
    errors = []
    for word, row in zip(words, gold):
        allowed = {'nsubj': {'subject'}, 'nsubj:pass': {'subject'}, 'obj': {'object'}}.get(row[7])
        if allowed and word['role'] not in allowed:
            errors.append(f"{word['surface']}: {word['role']}, UD {row[7]}")
    return errors


def semantic_errors(identity, words):
    errors = []
    form = {w['surface']: w for w in words}
    scopes = {
        'test-s22': {w: 'title' for w in ('Первое','Курс','Такси','Форсаж')},
        'test-s23': {'Писем':'title'},
        'test-s24': {'умершего':'negated', 'живого':'correction', 'сценой':'focus_negated',
                     'изображением':'correction', 'является':'cause'},
        'test-s25': {'Not':'title'},
        'test-s30': {'делать':'phase', 'визуально':'qualification'},
    }
    for surface, scope in scopes.get(identity, {}).items():
        if not any(w['surface'] == surface and w.get('scope') == scope for w in words):
            errors.append(f'{surface}: expected scope {scope}')
    references = {
        'test-s24': [('где','antecedent','иконографией'), ('умершего','controller','Христа')],
        'test-s25': [('которой','antecedent','автобиографию')],
        'test-s26': [('проблемами','controller','недостаток')],
        'test-s27': [('умеренный','controller','Климат')],
        'test-s28': [('пожалованного','coord_head','выехавшего')],
        'test-s29': [('представляют','controller','Такси'), ('собой','antecedent','Такси')],
        'test-s30': [('обтекаемыми','controller','автомобили'), ('аэродинамичными','controller','автомобили')],
    }
    for surface, field, target in references.get(identity, ()):
        head = form[surface].get(field)
        if head is None or words[head]['surface'] != target:
            errors.append(f'{surface}: expected {field} {target}')
    if identity == 'test-s22' and str(form['4'].get('quantity')) != '4':
        errors.append('Missing quantity 4')
    if identity == 'test-s23' and form['выдержанные']['assertion_status'] == 'asserted':
        errors.append('Participle detached from its attributive scope')
    if identity == 'test-s24' and words[0]['assertion_status'] != 'directive':
        errors.append('Missing directive scope')
    if identity == 'test-s25':
        if any(form[w].get('participant_ref') is not None for w in ('боюсь','измениться')):
            errors.append('The speaker inside the title was bound to a dialogue participant')
        if form['боюсь']['assertion_status'] != 'title':
            errors.append('Lost translated title scope')
        if form['изменить']['assertion_status'] == 'asserted':
            errors.append('Attempt recorded as an accomplished change')
    roles = {
        'test-s23': {'Писем':'genitive_modifier', 'людей':'genitive_modifier'},
        'test-s26': {'средств':'nominal_conjunct', 'вопросы':'nominal_conjunct', 'зданий':'genitive_modifier',
                     'проблемами':'predicative_complement'},
        'test-s29': {'Бангкок':'apposition', 'Таиланда':'genitive_modifier'},
    }
    for word, role in roles.get(identity, {}).items():
        if form[word]['role'] != role:
            errors.append(f'{word}: expected {role}')
    if identity == 'test-s27' and form['умеренный']['role'] != 'clause_conjunct':
        errors.append('Missing second predicate')
    if identity == 'test-s28' and form['Происходит']['assertion_status'] != 'qualified':
        errors.append('Lost the attribution to the genealogies')
    if identity == 'test-s29':
        if form['отличаются']['assertion_status'] != 'asserted':
            errors.append('Missing assertion of отличаются')
        if form['используемых']['role'] != 'governed' or form['используемых']['assertion_status'] != 'attributive':
            errors.append('Lost the substantivized participle under от')
    if identity == 'test-s30' and form['автомобили']['role'] != 'object':
        errors.append('Cars assigned the role of a performer')
    if identity == 'test-s31' and (form['Авиабаза']['role'] != 'subject' or
                                  (form['создана'].get('morphology') or {}).get('voice') != 'pssv'):
        errors.append('Missing passive subject or voice')
    return errors


def compare(words, gold, identity):
    issues = grammatical_errors(words, gold) + semantic_errors(identity, words)
    projected = [word['head'] for word in words]
    for i, word in enumerate(words):
        shared = word.get('coord_head')
        if (shared is not None and word['rule'] == words[shared]['rule'] == 'PART.ATTR'
                and word['head'] == words[shared]['head']):
            projected[i] = shared
    heads = mismatches(projected, [w['role'] for w in words], gold, [w['rule'] for w in words])
    return heads, issues


def reference_answer(identity, text, probe, gold):
    question = probe.question
    options = probe.options
    choices = set()
    source = 'UD'
    if 'if it is in the accusative case' in question:
        choices = {row[1] if 'Case=Acc' in row[5].split('|') else 'no such word'
                   for row in gold if f'«{row[1]}»' in question and 'Case=' in row[5]}
    elif 'if the verb presents the action as a bounded whole' in question:
        choices = {row[1] if 'Aspect=Perf' in row[5].split('|') else 'no such word'
                   for row in gold if f'«{row[1]}»' in question and 'Aspect=' in row[5]}
    elif identity == 'test-s25' and '«измениться»' in question and 'its unstated subject is the speaker' in question:
        choices = {'измениться'}
        source = 'control reading'
    elif 'несмотря на запятую между ними' in question:
        sites = [i for i, row in enumerate(gold) if 'InjectedComma' in row[9]]
        for i in sites:
            left, right = gold[i - 1], gold[i + 1]
            if left[6] == right[0] or right[6] == left[0]:
                choices.add(f'{left[1]}, {right[1]}')
        if not sites:
            choices = {'сохранить все запятые'}
    elif identity == 'test-s22' and 'перечислены как названия' in question:
        choices = {'службы'}
        source = 'control reading'
    elif identity == 'test-s22' and 'перечень отдельных названий' in question:
        choices = {'Первое Курс Такси + Форсаж'}
        source = 'control reading'
    elif identity == 'test-s25' and question == 'Какие слова дают второй вариант названия?':
        choices = {'Не боюсь измениться'}
        source = 'control reading'
    elif question.startswith('Какое существительное поясняет действие'):
        choices = {gold[int(row[6]) - 1][1] for row in gold if int(row[6]) and f'«{row[1]}»' in question}
    elif identity == 'test-s24' and question.startswith('Какое сокращение здесь означает'):
        choices = {'Ср.', 'Ср'}
        source = 'control reading'
    elif question == 'Какие слова вместе образуют название?':
        choices = {'test-s24': {'Муж скорбей'}, 'test-s23': {'Писем тёмных людей'}}.get(identity, set())
        source = 'control reading'
    elif 'характеризует согласованное определение' in question:
        choices = {gold[int(row[6]) - 1][1] for row in gold if row[7] == 'amod' and f'«{row[1]}»' in question}
    elif identity == 'test-s29' and 'Слово «Тук-тук»' in question and 'именем или названием' in question:
        choices = {'Тук-тук'}
        source = 'control reading'
    elif 'именем или названием' in question:
        choices = {row[1] for row in gold if row[3] == 'PROPN' and f'«{row[1]}»' in question}
    elif 'поясняет придаточная часть' in question:
        choices = {gold[int(row[6]) - 1][1] for row in gold if row[7] == 'acl:relcl'}
    elif 'передаёт оговорку' in question:
        source = 'control reading'
        choices = {o for o in options if identity == 'test-s28' and o.lower().startswith('по сказаниям')}
        if not choices:
            choices = {'нет такого сочетания'}
    elif 'Какое написание передаёт слово' in question:
        source = 'verbatim'
        choices = {options[0]}
    matches = [o for o in options if o in choices]
    return (matches[0], source) if len(matches) == 1 else ('?', 'unanswered')


def projection(words, gold):
    keep = [i for i in range(len(words)) if gold[i][3] != 'PUNCT']
    positions = {i: j for j, i in enumerate(keep)}
    result = []
    for i in keep:
        word = words[i]
        item = {k: word[k] for k in ('surface', 'morphology', 'participant_ref', *FIELDS) if word.get(k) is not None}
        for field in (*LINKS, 'quotation'):
            if word.get(field) is not None:
                item[field] = positions.get(word[field], 'punctuation')
        result.append(item)
    return result


def inspect(core, reply, text, gold, identity):
    result = {'status': reply.status, 'reason': reply.analysis.reason}
    good = 'DIRECTIVE' if identity == 'test-s24' else 'STORED'
    result['empty'] = not core.store.links() and not any(core.store.elements(domain) for domain in Domain)
    if result['empty'] != (reply.status != 'STORED'):
        raise ValueError('Memory changed on an incomplete reading or contains no committed observation')
    if reply.status not in {'DIRECTIVE', 'STORED'}:
        result['exact'] = False
        return result, None
    analyzed = reply.analysis
    aligned = align(analyzed.tokens, text, gold)
    if reply.status == 'STORED':
        group = core.store.get_element(Domain.H, reply.observation_ref)
        if group.meta['verbatim'] != text:
            raise ValueError('Verbatim observation changed')
        words = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
        edges = {(e.source, e.target, e.relation_id) for e in core.store.links()}
        for i, w in enumerate(words):
            for field in LINKS:
                if w.get(field) is None:
                    continue
                label = w['role'] if field == 'head' else field
                expected = (group.members[i], group.members[w[field]], 'grammar.' + label)
                if expected not in edges:
                    raise ValueError(f'Missing graph edge {expected}')
    else:
        words = _rows(analyzed, {})
    if len(analyzed.analyses) != 1 or any(r[3] != 'PUNCT' for r in aligned[len(words):]):
        raise ValueError('Incomplete token coverage')
    if any(w['surface'] != t.surface or text[t.start:t.end] != w['surface'] for w, t in zip(words, analyzed.tokens)):
        raise ValueError('Bad source span')
    heads, issues = compare(words, aligned, identity)
    graph = projection(words, aligned)
    result.update(exact=not heads and not issues and reply.status == good, incorrect_heads=heads,
                  role_scope_errors=issues, graph_sha256=digest(graph))
    return result, graph


@contextmanager
def time_limit(seconds):
    signal.setitimer(signal.ITIMER_PROF, seconds)
    try:
        yield
    finally:
        signal.setitimer(signal.ITIMER_PROF, 0)


def expire(*_):
    raise TimeoutError


def run(identity, variant, text, gold, seconds):
    record = {'id': identity, 'variant': variant, 'text': text}
    calls = []
    def choose(probe):
        answer, source = selector(probe)
        if answer not in (*probe.options, '?', '0'):
            raise ValueError('Teacher selected an unoffered option')
        calls.append({'question': probe.question, 'options': list(probe.options), 'answer': answer, 'source': source})
        return answer

    core = AHCore()
    selector = lambda p: ('?', 'abstain')
    try:
        with time_limit(seconds):
            reply = submit(core, text, choose)
            reading, graph = inspect(core, reply, text, gold, identity)
    except TimeoutError:
        if core.store.links() or any(core.store.elements(domain) for domain in Domain):
            raise ValueError('Timeout left a partial observation')
        return {**record, 'abstention': 'TIME_LIMIT', 'status': 'TIME_LIMIT', 'exact': False, 'empty': True, 'calls': calls}, None
    if calls and not reading['empty']:
        raise ValueError('Abstention changed memory')
    record.update(abstention=reply.status, abstention_empty=reading['empty'])
    if not reading['empty'] or reply.status == 'DIRECTIVE':
        record['abstention_exact'] = reading['exact']
    if not calls:
        return {**record, **reading, 'calls': []}, graph
    calls.clear()
    selector = lambda p: reference_answer(identity, text, p, gold)
    try:
        with time_limit(seconds):
            if not reply.analysis.analyses:
                first = submit(AHCore(), text, choose)
            else:
                first = reply
            parsed = first.analysis
            if parsed.analyses:
                aligned = align(parsed.tokens, text, gold)
                trees = parsed.analyses
                tokens = parsed.tokens[:len(trees[0])]
                def score(tree):
                    rows = _rows(replace(parsed, analyses=(tree,)), {})
                    heads, issues = compare(rows, aligned, identity)
                    lemmas = sum(w['lemma'].casefold().replace('ё','е') != row[2].casefold().replace('ё','е')
                                 for w, row in zip(rows, aligned) if row[3] != 'PUNCT')
                    return len(issues), len(heads), lemmas
                scores = {tree: score(tree) for tree in trees}
                target = min(trees, key=scores.get)
                def selector(p):
                    nonlocal trees, target
                    partition = _partition(trees, tokens, text) if len(trees) > 1 else None
                    if partition and p == partition[0]:
                        keys = partition[1]
                        answer = keys[trees.index(target)]
                        optimal = {key for tree, key in zip(trees, keys) if scores[tree] == scores[target]}
                        source = 'reference tree'
                        if len(optimal) > 1:
                            answer, source = reference_answer(identity, text, p, gold)
                            if answer not in optimal:
                                return '?', 'unanswered reference tie'
                        trees = tuple(tree for tree, key in zip(trees, keys) if key == answer)
                        target = min(trees, key=scores.get)
                        return answer, source
                    return reference_answer(identity, text, p, gold)
            core = AHCore()
            calls.clear()
            reply = submit(core, text, choose)
            reading, graph = inspect(core, reply, text, gold, identity)
    except TimeoutError:
        if core.store.links() or any(core.store.elements(domain) for domain in Domain):
            raise ValueError('Timeout left a partial observation')
        reading, graph = {'status':'TIME_LIMIT', 'exact':False, 'empty':True}, None
    return {**record, **reading, 'calls':calls}, graph


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=int, default=12)
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--expect', type=Path)
    args = parser.parse_args()
    signal.signal(signal.SIGPROF, expire)
    results = []
    for identity, raw, rows in batch(args.corpus):
        if args.ids and identity not in args.ids:
            continue
        reference = None
        for variant, text, gold in variants(raw, rows):
            result, graph = run(identity, variant, text, gold, args.seconds)
            if variant == 'original':
                reference = graph if result['exact'] else None
            if graph is not None:
                result['same_as_original'] = graph == reference if reference is not None else None
                if reference and graph != reference:
                    result['graph_differences'] = [
                        {'surface': item['surface'], 'field': k, 'original': old.get(k), 'observed': item.get(k)}
                        for old, item in zip(reference, graph) for k in sorted(old.keys() | item.keys())
                        if old.get(k) != item.get(k)]
            print(identity, variant, result['status'], result.get('reason'), result['exact'], flush=True)
            results.append(result)
    if args.expect:
        report = json.loads(args.expect.read_text())
        if report['seconds_per_stage'] != args.seconds or report['corpus_sha256'] != DIGEST:
            raise ValueError('Mismatched time limit or corpus in comparison')
        expected = {(r['id'], r['variant']): r for r in report['cases']}
    args.output.write_text(json.dumps({'corpus_sha256': DIGEST, 'seconds_per_stage': args.seconds,
                                       'cases': results}, ensure_ascii=False, indent=1) + '\n')
    if args.expect:
        for result in results:
            previous = expected[result['id'], result['variant']]
            if previous['exact'] and (not result['exact'] or previous['status'] != result['status']
                                      or previous['graph_sha256'] != result.get('graph_sha256')
                                      or result.get('same_as_original') is False):
                raise SystemExit(f"Changed accepted reading: {result['id']} {result['variant']}")




if __name__ == '__main__':
    main()
