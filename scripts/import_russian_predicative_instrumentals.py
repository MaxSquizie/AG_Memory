import csv
from collections import defaultdict
from argparse import ArgumentParser
from pathlib import Path


def governors(corpora, *, object_adjectives=False):
    lemmas = set()
    for corpus in corpora:
        for sentence in corpus.read_text(encoding='utf-8').split('\n\n'):
            rows = {}
            for line in sentence.splitlines():
                columns = line.split('\t')
                if len(columns) == 10 and columns[0].isdecimal():
                    rows[columns[0]] = columns
            for word in rows.values():
                governor = rows.get(word[6])
                pos = 'ADJ' if object_adjectives else 'NOUN'
                if not (word[7] == 'xcomp' and word[3] == pos and 'Case=Ins' in word[5].split('|')
                        and governor is not None and governor[3] == 'VERB'):
                    continue
                if object_adjectives and not any(r[7] == 'obj' and r[6] == governor[0] for r in rows.values()):
                    continue
                lemmas.add(governor[2].casefold())
    return sorted(lemmas)


def status_partners(lemmas, path):
    frames = defaultdict(list)
    with path.open(encoding='utf-8') as stream:
        for row in csv.DictReader(stream, delimiter='\t', quoting=csv.QUOTE_NONE):
            frames[row['ConstrIndex']].append(row)
    known = set(lemmas)
    expanded = set(known)
    for frame in frames.values():
        if not any(row['Form'] == 'Snom' for row in frame) or any(row['Form'] == 'Sacc' for row in frame):
            continue
        for row in frame:
            if row['Form'] == 'Sins' and row['Role'] == 'статус':
                related = {word.rstrip('0123456789') for word in row['KeyLexemes'].split(',')}
                if len(related) == 2 and related & known:
                    expanded.update(related)
    return sorted(expanded)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--status-frames', type=Path)
    parser.add_argument('--object-adjectives', action='store_true')
    parser.add_argument('corpora', nargs='+', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    verbs = governors(args.corpora, object_adjectives=args.object_adjectives)
    if args.status_frames:
        verbs = status_partners(verbs, args.status_frames)
    args.output.write_text(''.join(verb + '\n' for verb in verbs), encoding='utf-8')
