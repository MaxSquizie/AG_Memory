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


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('--object-adjectives', action='store_true')
    parser.add_argument('corpora', nargs='+', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(verb + '\n' for verb in governors(args.corpora, object_adjectives=args.object_adjectives)), encoding='utf-8')
