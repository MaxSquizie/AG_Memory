from argparse import ArgumentParser
from pathlib import Path
import re

from measure_russian_grammar import sentences


def entries(lexicon, corpus):
    entries = set(re.findall(r'^\s*"([^"]+)"', lexicon.read_text(encoding='utf-8-sig'), re.MULTILINE))
    pairs = set()
    for _, _, rows in sentences(corpus):
        for prep, noun in zip(rows, rows[1:]):
            phrase = ' '.join((prep[1].casefold(), noun[1].casefold()))
            parenthetical = noun[3] == 'NOUN' and noun[7] == 'parataxis'
            pronominal = noun[3] == 'PRON' and noun[7] in ('obl', 'parataxis')
            if (phrase in entries and prep[3] == 'ADP' and prep[6:8] == [noun[0], 'case']
                    and (parenthetical or pronominal)
                    and all(child[0] == prep[0] or child[3] == 'PUNCT' for child in rows if child[6] == noun[0])):
                pairs.add((phrase, prep[2], noun[2], noun[3]))
    return sorted(pairs)


if __name__ == '__main__':
    parser = ArgumentParser()
    for name in ('lexicon', 'corpus', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join('\t'.join(row) + '\n' for row in entries(args.lexicon, args.corpus)), encoding='utf8')
