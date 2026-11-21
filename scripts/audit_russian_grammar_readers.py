import argparse
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
                                evaluate=lambda w, g, i: compare(w, g, i, lambda *_: []))
            record.update(result)
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
    parser.add_argument('--readings', type=Path)
    parser.add_argument('--start', type=int, default=72)
    parser.add_argument('--count', type=int, default=20)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    if hashlib.sha256(args.corpus.read_bytes()).hexdigest() != DIGEST:
        parser.error('Unexpected corpus revision')
    if min(args.start, args.count, args.seconds) < 1:
        parser.error('Expected positive bounds')
    readings = json.loads(args.readings.read_text()) if args.readings else {}
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
