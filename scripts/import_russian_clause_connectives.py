from argparse import ArgumentParser
from pathlib import Path


def entries(paths, *, nominal=False, preposed=False):
    rows = set()
    for path in paths:
        for sentence in path.read_text(encoding='utf-8').split('\n\n'):
            words = {}
            for line in sentence.splitlines():
                columns = line.split('\t')
                if len(columns) == 10 and columns[0].isdecimal():
                    words[int(columns[0])] = columns
            for index, word in words.items():
                if word[3] not in ('CCONJ', 'SCONJ') or word[7] not in ('cc', 'mark'):
                    continue
                child = words.get(int(word[6]))
                if not child:
                    continue
                if not nominal and child[3] not in ('VERB', 'ADJ', 'ADV', 'AUX', 'NOUN'):
                    continue
                governor = words.get(int(child[6]))
                if not governor:
                    continue
                if nominal and (word[3] != 'CCONJ' or word[7] != 'cc' or child[7] != 'conj'
                                or child[3] not in ('NOUN', 'PROPN', 'PRON')
                                or governor[3] not in ('NOUN', 'PROPN', 'PRON')):
                    continue
                relation = child[7]
                if (word[7], relation) not in (('cc', 'conj'), ('mark', 'advcl'), ('mark', 'ccomp')):
                    continue
                parts = sorted([index] + [i for i, w in words.items() if w[6] == str(index) and w[7] == 'fixed'])
                if parts != list(range(parts[0], parts[-1] + 1)):
                    continue
                if preposed and (relation != 'advcl' or parts[0] != min(words) or int(child[0]) >= int(governor[0])):
                    continue
                form = ' '.join(words[i][1].casefold().replace('ё', 'е') for i in parts)
                head = governor[2].casefold().replace('ё', 'е') if relation == 'ccomp' else '*'
                rows.add((form, relation, head))
    return sorted(rows)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('corpora', nargs='+', type=Path)
    parser.add_argument('output', type=Path)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument('--nominal', action='store_true')
    mode.add_argument('--preposed', action='store_true')
    args = parser.parse_args()
    args.output.write_text(''.join('\t'.join(row) + '\n' for row in entries(args.corpora, nominal=args.nominal, preposed=args.preposed)), encoding='utf-8')
