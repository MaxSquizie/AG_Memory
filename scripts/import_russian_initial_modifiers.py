from argparse import ArgumentParser
from pathlib import Path


def entries(path):
    pairs = set()
    for sentence in path.read_text(encoding='utf8').split('\n\n'):
        rows = {}
        for line in sentence.splitlines():
            cols = line.split('\t')
            if len(cols) == 10 and cols[0].isdecimal():
                rows[int(cols[0])] = cols
        for index, word in rows.items():
            if word[7] not in {'advmod', 'discourse', 'parataxis'}:
                continue
            head = rows.get(int(word[6]))
            if head is None or head[3] not in {'VERB', 'AUX', 'ADJ'}:
                continue
            parts = [i for i, row in rows.items() if row[6:8] == [word[0], 'fixed']]
            if not parts or parts != list(range(index + 1, index + 1 + len(parts))):
                continue
            after = rows.get(parts[-1] + 1)
            if after and after[1] == ',' and (index == 1 or rows[index - 1][1] == ','):
                expression = [word, *(rows[i] for i in parts)]
                pairs.add(tuple(' '.join(row[field].casefold() for row in expression) for field in (1, 2)))
    return sorted(pairs)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(f'{form}\t{lemmas}\n' for form, lemmas in entries(args.corpus)), encoding='utf8')
