from argparse import ArgumentParser
from pathlib import Path

from import_russian_bare_government import read_infinitives


def infinitive(row):
    return row[7] in {'csubj', 'xcomp'} and 'VerbForm=Inf' in row[5].split('|')


def plain_infinitive(row, children):
    return infinitive(row) and not any(
        dep[7] in {'nsubj', 'expl'} or {'PronType=Rel', 'PronType=Int'}.intersection(dep[5].split('|'))
        for dep in children.get(row[0], ()))


def bare_dative(row, children):
    return (row[7] in {'iobj', 'obl', 'obj'} and 'Case=Dat' in row[5].split('|')
            and not any(dep[7] == 'case' for dep in children.get(row[0], ())))


def governors(corpora, perfective):
    lemmas = set()
    with_infinitive = set()
    for path in corpora:
        for block in path.read_text(encoding='utf8').split('\n\n'):
            rows = [fields for line in block.splitlines()
                    if len(fields := line.split('\t')) == 10 and fields[0].isdecimal()]
            children = {}
            for row in rows:
                children.setdefault(row[6], []).append(row)
            for word in rows:
                feats = set(word[5].split('|'))
                if word[3] != 'VERB' or not {'VerbForm=Fin', 'Number=Sing'} <= feats:
                    continue
                if not {'Gender=Neut', 'Person=3'} & feats:
                    continue
                dependents = children.get(word[0], ())
                if (not any(child[7].startswith('nsubj') for child in dependents)
                        and any(infinitive(child) for child in dependents)):
                    with_infinitive.add(word[2].casefold())
                arguments = [child for child in dependents
                             if child[7] not in {'punct', 'mark', 'cc', 'conj', 'advcl'}]
                if len(arguments) != 2:
                    continue
                if any(plain_infinitive(child, children) for child in arguments) and any(
                        bare_dative(child, children) for child in arguments):
                    lemmas.add(word[2].casefold())
    _, pairs = read_infinitives(perfective)
    partners = {b for a, b in pairs if a in lemmas} | {a for a, b in pairs if b in lemmas}
    return sorted(lemmas | (partners & with_infinitive))


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('perfective', type=Path)
    parser.add_argument('corpora', nargs='+', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(verb + '\n' for verb in governors(args.corpora, args.perfective)), encoding='utf8')
