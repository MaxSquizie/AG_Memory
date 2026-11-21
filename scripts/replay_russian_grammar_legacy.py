import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import signal

from accept_russian_grammar_second_ten import DIGEST
from audit_russian_grammar_third_ten import expire, time_limit, variants
from measure_russian_grammar import sentences
from ah.core import AHCore
from ah.model import Domain
from ah.russian_grammar.memory import submit


class MissingReading(Exception):
    pass


def previous_answers(directory):
    answers = defaultdict(set)
    for path in sorted(directory.glob('russian_grammar_*ten/*blind*.json')):
        pending = [json.loads(path.read_text(encoding='utf8'))]
        while pending:
            item = pending.pop()
            if isinstance(item, list):
                pending.extend(item)
            elif isinstance(item, dict):
                if {'context', 'question', 'options', 'answer'} <= item.keys():
                    key = (item['context'], item['question'], tuple(item['options']))
                    answers[key].add(item['answer'])
                else:
                    pending.extend(item.values())
    return answers


def replay(text, answers, seconds):
    memory = AHCore()
    prompts = []

    def choose(probe):
        key = (probe.context, probe.question, probe.options)
        labels = answers.get(key, ())
        prompts.append(hashlib.sha256(probe.prompt().encode()).hexdigest())
        if len(labels) != 1:
            raise MissingReading
        return next(iter(labels))

    checksum = None
    reason = None
    try:
        with time_limit(seconds):
            reply = submit(memory, text, choose)
        status = reply.status
        reason = reply.analysis.reason
        if status == 'STORED':
            chunk = memory.store.get_element(Domain.H, reply.observation_ref)
            rows = [memory.store.get_element(Domain.H, node.uid).meta for node in chunk.members]
            wire = json.dumps(rows, ensure_ascii=False, sort_keys=True).encode()
            checksum = hashlib.sha256(wire).hexdigest()
    except MissingReading:
        status = 'MISSING_READING'
    except TimeoutError:
        status = 'TIME_LIMIT'
    if status != 'STORED' and (memory.store.links() or any(memory.store.elements(d) for d in Domain)):
        raise ValueError('An incomplete reading changed memory')
    return dict(status=status, reason=reason, calls=prompts, row_metadata_sha256=checksum)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--seconds', type=int, default=30)
    args = parser.parse_args()
    if args.seconds <= 0 or hashlib.sha256(args.corpus.read_bytes()).hexdigest() != DIGEST:
        parser.error('Expected a positive time limit and the pinned GSD test file')
    answers = previous_answers(Path(__file__).resolve().parents[1] / 'docs/evidence')
    signal.signal(signal.SIGPROF, expire)
    records = []
    for identity, sentence, rows in sentences(args.corpus):
        number = int(identity.split('-s')[1])
        if 22 <= number <= 61:
            kind = 'no_punctuation' if number <= 41 else 'original'
            text = next(text for variant, text, _ in variants(sentence, rows) if variant == kind)
            records.append(dict(id=identity, variant=kind, **replay(text, answers, args.seconds)))
    args.output.write_text(json.dumps(records, ensure_ascii=False, indent=2) + '\n', encoding='utf8')


if __name__ == '__main__':
    main()
