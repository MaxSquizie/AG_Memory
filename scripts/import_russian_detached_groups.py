from argparse import ArgumentParser
from pathlib import Path


def entries(source):
    pairs = set()
    for sentence in source.read_text(encoding='utf8').split('\n\n'):
        rows = {}
        for line in sentence.splitlines():
            fields = line.split('\t')
            if len(fields) == 10 and fields[0].isdecimal():
                rows[int(fields[0])] = fields
        children = {}
        for index, row in rows.items():
            children.setdefault(int(row[6]), []).append(index)
        for prep, row in rows.items():
            noun = int(row[6])
            nominal = rows.get(noun)
            if row[3] != 'ADP' or row[7] != 'case' or not nominal or nominal[3] != 'NOUN':
                continue
            if nominal[7] not in {'obl', 'parataxis', 'nmod'} or not any(
                    rows[i][7] in {'nmod', 'det', 'nmod:poss'} for i in children.get(noun, ())):
                continue
            members = set()
            pending = [noun]
            while pending:
                i = pending.pop()
                if i not in members and rows[i][3] != 'PUNCT':
                    members.add(i)
                    pending.extend(children.get(i, ()))
            end = max(members) + 1
            if members != set(range(prep, end)) or prep - 1 not in rows or end not in rows:
                continue
            host = int(nominal[6])
            if host <= end or rows[host][3] not in {'VERB', 'AUX', 'ADJ'}:
                continue
            if rows[prep - 1][1] == rows[end][1] == ',':
                pairs.add((row[2].casefold(), nominal[2].casefold()))
    return sorted(pairs)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('train', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(f'{prep}\t{noun}\n' for prep, noun in entries(args.train)), encoding='utf8')
