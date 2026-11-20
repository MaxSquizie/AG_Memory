import argparse
import csv
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import signal

from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import _rows, submit
from ah.russian_grammar.parser import _partition
from measure_russian_grammar import sentences


BASELINE = Path(__file__).resolve().parents[1] / 'docs/evidence/russian_grammar_audit/corpus.tsv'
DIGEST = 'fa3642959614db06fdab2d7464af8a0873c70d0a2b5758758231d0ef725821ea'


def sample(path):
    if hashlib.sha256(path.read_bytes()).hexdigest() != DIGEST:
        raise ValueError('Unexpected Russian-GSD revision')
    with BASELINE.open() as source:
        failures = [row['sent_id'] for row in csv.DictReader(source, delimiter='\t') if row['after'] != 'STORED']
    return [case for case in sentences(path) if case[0] in failures[10:20]]


def align(surfaces, rows):
    groups = []
    cursor = 0
    for surface in surfaces:
        start = cursor
        word = ''
        while cursor < len(rows) and len(word) < len(surface):
            if cursor > start and 'SpaceAfter=No' not in rows[cursor - 1][9]:
                return None
            word += rows[cursor][1]
            cursor += 1
        if word != surface:
            return None
        groups.append(tuple(range(start, cursor)))
    owner = {j: i for i, group in enumerate(groups) for j in group}
    if cursor != len(rows):
        return None
    aligned = []
    for surface, group in zip(surfaces, groups):
        external = [j for j in group if int(rows[j][6]) - 1 not in group]
        if len(external) != 1:
            return None
        row = rows[external[0]].copy()
        row[1] = surface
        row[6] = str(owner.get(int(row[6]) - 1, -1) + 1)
        aligned.append(row)
    return aligned


def mismatches(heads, roles, gold, rules):
    normalized = list(heads)
    for i, (head, role) in enumerate(zip(heads, roles)):
        if role == 'governed' and head is not None and roles[head] == 'preposition':
            normalized[i], normalized[head] = heads[head], i
    for marker, rule in enumerate(rules):
        right = heads[marker]
        left = marker - 1
        if (rule == 'A.COORD' and right is not None and left >= 0 and roles[left] == roles[right] == 'attribute'
                and heads[left] == heads[right]):
            normalized[right] = normalized[left] if normalized[left] != heads[left] else left
    return [(row[1], int(row[6]), 0 if normalized[i] is None else normalized[i] + 1)
            for i, row in enumerate(gold) if row[3] != 'PUNCT'
            and (0 if normalized[i] is None else normalized[i] + 1) != int(row[6])]


PARTICIPANT_ROLES = {'nsubj': {'subject'}, 'nsubj:pass': {'subject'},
                     'obj': {'object'}, 'iobj': {'recipient', 'experiencer'}}
EXPECTED_STATUS = {
    'test-s12': {'срублено': 'negated', 'находится': 'asserted', 'может': 'qualified'},
    'test-s13': {'Деятельность': 'heading'},
    'test-s15': {'предложил': 'asserted', 'вывести': 'embedded'},
    'test-s16': {'необходим': 'asserted', 'сделав': 'qualified', 'привлекательным': 'qualified'},
    'test-s18': {'мужчина': 'parenthetical', 'ходит': 'parenthetical', 'подходит': 'asserted'},
    'test-s19': {'идти': 'modal'},
    'test-s20': {'получила': 'asserted', '17': 'parenthetical', '5': 'parenthetical'},
}
EXPECTED_CONTROLLERS = {
    'test-s16': {'привлекательным': 'его'}, 'test-s17': {'посылал': 'Хан'}, 'test-s18': {'ходит': 'мужчина'}, 'test-s19': {'идти': 'малыш'}
}


INTERPRETATIONS = {
    'test-s16': {
        'Какое существительное подразумевается после «существующей»?': 'инфраструктуры',
        'Какие слова вместе образуют название?': 'Орёл -- Южный',
        'К какому участнику в тексте относится действие «сделав»?': 'ремонт и строительство',
    }
}


def participant_errors(roles, gold):
    return [(row[1], row[7], role) for role, row in zip(roles, gold)
            if row[7] in PARTICIPANT_ROLES and role not in PARTICIPANT_ROLES[row[7]]]


def scope_errors(identity, words):
    errors = []
    for word, expected in EXPECTED_STATUS.get(identity, {}).items():
        if not any(row['surface'] == word and row['assertion_status'] == expected for row in words):
            errors.append(f'{word}: expected status {expected}')
    for word, expected in EXPECTED_CONTROLLERS.get(identity, {}).items():
        if not any(row['surface'] == word and row['controller'] is not None and
                   words[row['controller']]['surface'] == expected for row in words):
            errors.append(f'{word}: expected controller {expected}')
    return errors


def read_graph(core, reply, text, gold, identity):
    group = core.store.get_element(Domain.H, reply.observation_ref)
    words = [core.store.get_element(Domain.H, member.uid).meta for member in group.members]
    links = {(link.source, link.target, link.relation_id) for link in core.store.links()}
    errors = []
    surfaces = [t.surface for t in reply.analysis.tokens]
    aligned = align(surfaces, gold)
    if group.meta['verbatim'] != text or not aligned or [row['surface'] for row in words] != surfaces[:len(words)]:
        errors.append('unaligned text')
    if any(row[3] != 'PUNCT' for row in (aligned or gold)[len(words):]):
        errors.append('missing units')
    for i, row in enumerate(words):
        for key in ('head', 'controller', 'antecedent', 'ellipsis_source', 'coord_head', 'shared_agent', 'shared_object'):
            if row.get(key) is not None:
                relation = 'grammar.' + (row['role'] if key == 'head' else key)
                if (group.members[i], group.members[row[key]], relation) not in links:
                    errors.append(f'missing link {i} {key}')
    if errors:
        return {'errors': errors}
    differences = mismatches([w['head'] for w in words], [w['role'] for w in words], aligned, [w['rule'] for w in words])
    errors.extend(participant_errors([row['role'] for row in words], aligned))
    errors.extend(scope_errors(identity, words))
    if identity == 'test-s16':
        ellipsis = next(w for w in words if w['surface'] == 'существующей')
        source = ellipsis.get('ellipsis_source')
        if source is None or words[source]['surface'] != 'инфраструктуры' or ellipsis['antecedent'] is not None:
            errors.append('ellipsis must identify its lexical source separately from coreference')
    if identity == 'test-s12':
        relative = next(w for w in words if w['surface'] == 'которому')
        anchor = relative.get('antecedent')
        if anchor is None or words[anchor]['surface'] != 'дуб':
            errors.append('age bearer must refer to the oak')
    if identity == 'test-s20':
        for form in ('769125', '17', '4', '5'):
            if not any(w['surface'] == form and str(w.get('quantity')) == form for w in words):
                errors.append(f'missing numeric value {form}')
    return {'errors': errors, 'differences': differences,
            'merged_units': len(gold) - len(aligned),
            'rows': [[w['surface'], w['role'], w['head'], w.get('controller'), w['assertion_status']] for w in words]}


def run(case, mode, answers):
    identity, text, gold = case
    core = AHCore()
    calls = []
    selector = None
    if mode in ('teacher', 'corpus-only'):
        def preliminary(probe):
            if 'поясняет придаточная часть' in probe.question:
                heads = {gold[int(row[6]) - 1][1] for row in gold if row[7] == 'acl:relcl' and int(row[6])}
                matches = [label for label in probe.options if label in heads]
                return matches[0] if len(matches) == 1 else '?'
            if 'вершиной первой именной группы' in probe.question:
                members = [i for i, row in enumerate(gold) if row[1] in probe.options]
                heads = [gold[i][1] for i in members if int(gold[i][6]) - 1 not in members]
                return heads[0] if len(heads) == 1 else '?'
            return '?'
        initial = submit(AHCore(), text, preliminary)
        parsed = initial.analysis
        aligned = align([token.surface for token in parsed.tokens], gold) if parsed else None
        if parsed and parsed.analyses and aligned:
            trees = parsed.analyses
            tokens = parsed.tokens[:len(trees[0])]
            def score(tree):
                differences = mismatches([l.head for l in tree], [l.role for l in tree], aligned, [l.rule for l in tree])
                lemmas = sum(link.lemma.casefold().replace('ё','е') != row[2].casefold().replace('ё','е')
                             for link, row in zip(tree, aligned) if row[3] != 'PUNCT')
                roles = participant_errors([link.role for link in tree], aligned)
                words = _rows(replace(parsed, analyses=(tree,)), {})
                return len(roles) + len(scope_errors(identity, words)), len(differences), lemmas
            target = min(trees, key=score)
            def select(probe):
                nonlocal trees
                if (answer := preliminary(probe)) != '?':
                    return answer
                partition = _partition(trees, tokens, text) if len(trees) > 1 else None
                if partition and partition[0] == probe:
                    keys = partition[1]
                    answer = keys[trees.index(target)]
                    trees = tuple(tree for tree, key in zip(trees, keys) if key == answer)
                    return answer
                if mode == 'teacher':
                    reading = INTERPRETATIONS.get(identity, {}).get(probe.question)
                    if reading in probe.options:
                        return reading
                if len(probe.options) == 1 and 'характеризует согласованное определение' in probe.question:
                    label, = probe.options
                    if any(row[7] == 'amod' and f'«{row[1]}»' in probe.question and
                           aligned[int(row[6]) - 1][1] == label for row in aligned):
                        return label
                if len(probe.options) == 1 and 'именем или названием' in probe.question:
                    label, = probe.options
                    if any(row[1] == label and row[3] == 'PROPN' for row in aligned):
                        return label
                return '?'
            selector = select
    def choose(probe):
        if mode == 'blind':
            transcript = answers.get(identity, [])
            message = transcript[len(calls)] if len(calls) < len(transcript) else {}
            if (message.get('question'), message.get('options'), message.get('context')) != (
                    probe.question, list(probe.options), probe.context):
                raise ValueError('blind transcript does not match current probe')
            answer = message['answer']
        else:
            answer = selector(probe) if selector else '?'
        calls.append({'context': probe.context, 'question': probe.question, 'options': list(probe.options), 'answer': answer})
        return answer
    reply = submit(core, text, choose)
    result = {'id': identity, 'mode': mode, 'status': reply.status, 'reason': reply.analysis.reason, 'calls': calls}
    if reply.status == 'STORED':
        result.update(read_graph(core, reply, text, gold, identity))
        result['exact'] = not result['errors'] and not result.get('differences')
    else:
        result['empty'] = not core.store.links() and not any(core.store.elements(domain) for domain in Domain)
        result['exact'] = False
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--responses', type=Path)
    parser.add_argument('--ids', nargs='+')
    parser.add_argument('--require', choices=('teacher', 'blind'), default='teacher')
    parser.add_argument('--seconds', type=int, default=15)
    args = parser.parse_args()
    answers = json.loads(args.responses.read_text()) if args.responses else {}
    def expire(*_):
        raise TimeoutError
    signal.signal(signal.SIGPROF, expire)
    results = []
    for case in sample(args.corpus):
        identity = case[0]
        if args.ids and identity not in args.ids:
            continue
        for mode in ('abstain', 'teacher', 'corpus-only', 'blind'):
            if mode == 'corpus-only' and identity not in INTERPRETATIONS:
                continue
            if mode == 'blind' and identity not in answers:
                continue
            try:
                signal.setitimer(signal.ITIMER_PROF, args.seconds)
                result = run(case, mode, answers)
            except TimeoutError:
                result = {'id': identity, 'mode': mode, 'status': 'TIMEOUT', 'exact': False}
            finally:
                signal.setitimer(signal.ITIMER_PROF, 0)
            results.append(result)
            print(identity, mode, result['status'], result.get('reason'), result['exact'], flush=True)
    chosen = {record['id'] for record in results}
    passed = {r['id'] for r in results if r['mode'] == args.require and r['exact']}
    safe = all(r.get('empty') or r.get('exact') for r in results if r['mode'] == 'abstain')
    report = {'corpus_sha256': DIGEST, 'required_mode': args.require, 'passed': len(passed),
              'total': len(chosen), 'safe_abstention': safe, 'cases': results}
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=1)+'\n')
    return 0 if chosen and passed == chosen and safe else 1


if __name__ == '__main__':
    raise SystemExit(main())
