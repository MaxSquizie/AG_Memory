import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import signal

from accept_russian_grammar_second_ten import DIGEST
from audit_russian_grammar_fourth_ten import project
from audit_russian_grammar_third_ten import compare, expire, inspect, time_limit, variants
from measure_russian_grammar import sentences
from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


class MissingReading(Exception):
    pass


def eligible(rows):
    for _, surface, _, pos, tag, features, *_ in rows:
        if 'Foreign=Yes' in features.split('|') or tag == 'FW':
            return False
        if tag == 'ORD' and pos in {'ADJ', 'NUM'} and set(surface) <= set('IVXLCDM'):
            continue
        if any(ch.isalpha() and ch.casefold() not in 'абвгдеёжзийклмнопрстуфхцчшщъыьэюя' for ch in surface):
            return False
    return True


def name_coordination_errors(words, gold):
    errors = []
    for word, row in zip(words, gold):
        if ((word['role'] == 'nominal_conjunct' and row[7] == 'flat:name')
                or (word['role'] == 'name_part' and row[7] == 'conj')):
            errors.append(f"{word['surface']}: {word['role']}, UD {row[7]}")
    return errors


def evaluate(words, gold, identity):
    heads, errors = compare(words, gold, identity, lambda *_: [])
    return heads, errors + name_coordination_errors(words, gold)


def audit(identity, kind, text, rows, readings, seconds):
    calls = []
    core = AHCore()
    record = dict(id=identity, variant=kind, text=text, calls=calls)

    def choose(probe):
        prompt = probe.prompt()
        key = hashlib.sha256(prompt.encode()).hexdigest()
        saved = readings.get(key)
        if saved is None:
            record.update(pending={key: prompt})
            raise MissingReading
        if saved['prompt'] != prompt or saved['answer'] not in (*probe.options, '0', '?'):
            raise ValueError(f'Invalid reading {key}')
        calls.append(key)
        return saved['answer']

    try:
        with time_limit(seconds):
            reply = submit(core, text, choose)
            record.update(status=reply.status, reason=reply.analysis.reason)
            result, _ = inspect(core, reply, text, rows, identity, project=project,
                                evaluate=evaluate)
            record.update(result)
            if reply.status == 'STORED':
                observation = core.store.get_element(Domain.H, reply.observation_ref)
                words = [core.store.get_element(Domain.H, ref.uid).meta for ref in observation.members]
                wire = json.dumps([observation.meta, words], sort_keys=True, ensure_ascii=False,
                                  separators=(',', ':')).encode()
                record['stored_metadata_sha256'] = hashlib.sha256(wire).hexdigest()
            elif reply.analysis.status == 'PARSED_FRAGMENT' and len(reply.analysis.analyses) == 1:
                record['fragment'] = [
                    {**asdict(token), 'role': link.role, 'head': link.head, 'scope': link.scope}
                    for token, link in zip(reply.analysis.tokens, reply.analysis.analyses[0])
                ]
    except MissingReading:
        record['status'] = 'AWAITING_READER'
    except TimeoutError:
        record['status'] = 'TIME_LIMIT'
    empty = not core.store.links() and not any(core.store.elements(domain) for domain in Domain)
    if empty != (record['status'] != 'STORED'):
        raise ValueError(f'Unexpected memory state on {identity}/{kind}')
    record['empty'] = empty
    return record


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--readings', type=Path, action='append', default=[])
    parser.add_argument('--start', type=int, default=72)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    if hashlib.sha256(args.corpus.read_bytes()).hexdigest() != DIGEST:
        parser.error('Unexpected corpus revision')
    if min(args.start, args.count, args.seconds) < 1:
        parser.error('Expected positive bounds')
    readings = {}
    for path in args.readings:
        for key, entry in json.loads(path.read_text(encoding='utf8')).items():
            if key in readings and readings[key] != entry:
                parser.error(f'Conflicting reader records for {key}')
            readings[key] = entry
    signal.signal(signal.SIGPROF, expire)
    selected = []
    skipped = []
    for identity, text, rows in sentences(args.corpus):
        if int(identity.split('-s')[1]) < args.start:
            continue
        if eligible(rows):
            selected.append((identity, text, rows))
            if len(selected) == args.count:
                break
        else:
            skipped.append(identity)
    if len(selected) != args.count:
        parser.error('Not enough eligible sentences')
    results = [audit(identity, kind, source, gold, readings, args.seconds)
               for identity, text, rows in selected for kind, source, gold in variants(text, rows)]
    args.output.write_text(json.dumps(dict(corpus_sha256=DIGEST, skipped=skipped, results=results),
                                      ensure_ascii=False, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
