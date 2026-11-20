import argparse
from pathlib import Path


def abbreviations(path):
    found = set()
    for block in path.read_text(encoding='utf8').split('\n\n'):
        rows = [row.split('\t') for row in block.splitlines() if row.split('\t')[0].isdecimal()]
        for numeral, noun in zip(rows, rows[1:]):
            if numeral[6] != noun[0] or numeral[7] not in ('amod', 'nummod', 'nummod:gov'):
                continue
            if not numeral[1].isupper() or not set(numeral[1]) <= set('IVXLCDM') or 'ORD' not in numeral[4]:
                continue
            if noun[3] != 'NOUN' or not noun[1].endswith('.') or not noun[1][:-1].isalpha() or not noun[2].isalpha():
                continue
            for prep in rows:
                if prep[3] == 'ADP' and prep[6:8] == [noun[0], 'case'] and int(prep[0]) < int(numeral[0]):
                    cases = [v[5:] for v in noun[5].split('|') if v.startswith('Case=')]
                    for case in cases:
                        found.add((noun[1][:-1].casefold(), noun[2].casefold(), prep[2].casefold(), case))
    return sorted(found)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join('\t'.join(row) + '\n' for row in abbreviations(args.corpus)), encoding='utf8')
