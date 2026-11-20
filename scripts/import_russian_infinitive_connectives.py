from argparse import ArgumentParser
from pathlib import Path


def entries(path):
    result = set()
    for block in path.read_text(encoding='utf8').split('\n\n'):
        rows = {int(f[0]): f for line in block.splitlines()
                if len(f := line.split('\t')) == 10 and f[0].isdigit()}
        for i, conjunction in rows.items():
            if conjunction[3] != 'SCONJ' or conjunction[7] != 'mark':
                continue
            subordinate = rows.get(int(conjunction[6]))
            if not subordinate or subordinate[7] != 'advcl' or 'VerbForm=Inf' not in subordinate[5].split('|'):
                continue
            left = i - 1
            if left in rows and rows[left][1] == ',':
                left -= 1
            adverb = rows.get(left)
            if adverb and adverb[3] == 'ADV' and adverb[7] == 'advmod' and adverb[6] in (subordinate[6], conjunction[6]):
                result.add((adverb[2], conjunction[2]))
    return sorted(result)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('training', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(f'{adv}\t{conj}\n' for adv, conj in entries(args.training)), encoding='utf8')
