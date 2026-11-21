from argparse import ArgumentParser
from pathlib import Path


def entries(path):
    rows = set()
    for sentence in path.read_text(encoding='utf8').split('\n\n'):
        words = {}
        for line in sentence.splitlines():
            columns = line.split('\t')
            if len(columns) == 10 and columns[0].isdecimal():
                words[int(columns[0])] = columns
        for index, word in words.items():
            head = words.get(int(word[6]))
            if head is None or word[7] != 'advmod':
                continue
            if word[3] == 'PART' and head[3] in {'ADJ', 'DET'} and index == int(head[0]) + 1:
                rows.add(('postpositive', word[1].casefold()))
            if (word[3] == 'PART' and head[3] in {'NOUN', 'PROPN', 'PRON'}
                    and 'Polarity=Neg' not in word[5] and index == int(head[0]) - 1):
                rows.add(('prenominal', word[2]))
            if head[3] not in {'VERB', 'AUX'} or word[3] not in {'ADV', 'PART', 'SCONJ'}:
                continue
            negative = words.get(index + 1)
            if (word[3] == 'PART' and negative and 'Polarity=Neg' in negative[5]
                    and negative[6:8] == [head[0], 'advmod'] and index + 2 == int(head[0])):
                rows.add(('prenegative', word[2]))
            parts = [j for j, other in words.items() if other[6] == word[0] and other[7] == 'fixed']
            if parts and sorted(parts) == list(range(index + 1, index + len(parts) + 1)):
                rows.add(('adverbial', ' '.join(words[j][1].casefold()
                                                for j in range(index, index + len(parts) + 1))))
    return sorted(rows)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join('\t'.join(row) + '\n' for row in entries(args.corpus)), encoding='utf8')
