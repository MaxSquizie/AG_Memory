from argparse import ArgumentParser
from pathlib import Path


def governors(corpora):
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
                if (word[7] == 'xcomp' and word[3] == 'NOUN' and 'Case=Ins' in word[5].split('|')
                        and governor is not None and governor[3] == 'VERB'):
                    lemmas.add(governor[2].casefold())
    return sorted(lemmas)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('corpora', nargs='+', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(verb + '\n' for verb in governors(args.corpora)), encoding='utf-8')
