from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path


def entries(corpus):
    lemmas = set()
    for sentence in corpus.read_text(encoding='utf8').split('\n\n'):
        words = {}
        children = defaultdict(list)
        for line in sentence.splitlines():
            word = line.split('\t')
            if len(word) == 10 and word[0].isdecimal():
                words[word[0]] = word
                children[word[6]].append(word)
        for noun in words.values():
            if noun[3] != 'NOUN' or noun[7] != 'nsubj' or 'Case=Nom' not in noun[5] or 'Number=Sing' not in noun[5]:
                continue
            verb = words.get(noun[6])
            if not verb or verb[3] not in {'AUX', 'VERB'} or 'Number=Plur' not in verb[5] or 'VerbForm=Fin' not in verb[5]:
                continue
            dependents = children[noun[0]]
            if any(child[7] == 'conj' for child in dependents):
                continue
            if any(child[7] == 'nmod' and child[3] in {'NOUN', 'PROPN'} and 'Case=Gen' in child[5]
                   and 'Number=Plur' in child[5] and not any(edge[7] == 'case' for edge in children[child[0]])
                   for child in dependents):
                lemmas.add(noun[2])
    return lemmas


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text(''.join(word + '\n' for word in sorted(entries(args.corpus))), encoding='utf8')
