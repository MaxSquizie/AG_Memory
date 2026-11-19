import argparse
from collections import Counter
import hashlib
import json
from multiprocessing import Pool
from pathlib import Path
import signal

from ah.core import AHCore
from ah.russian_grammar.memory import submit


def sentences(path):
    for block in path.read_text(encoding='utf8').strip().split('\n\n'):
        fields = dict(line[2:].split(' = ', 1) for line in block.splitlines()
                      if line.startswith('# ') and ' = ' in line)
        rows = [line.split('\t') for line in block.splitlines() if line.split('\t')[0].isdigit()]
        if rows:
            yield fields['sent_id'], fields['text'], rows


def evaluate(case):
    identity, sentence, rows = case
    probes = []

    def expire(*args):
        raise TimeoutError

    def abstain(probe):
        probes.append(probe.question)
        return '?'

    signal.signal(signal.SIGPROF, expire)
    signal.setitimer(signal.ITIMER_PROF, 3)
    result = {'id': identity, 'words': sum(r[3] != 'PUNCT' for r in rows)}
    try:
        reply = submit(AHCore(), sentence, abstain)
        result.update(status=reply.status, reason=reply.analysis.reason if reply.analysis else '',
                      complete=bool(reply.analysis and reply.analysis.status == 'PARSED_FRAGMENT'),
                      reductions=sum(s.outcome == 'selected' and s.after < s.before
                                     for s in getattr(reply.analysis, 'steps', ())))
        if reply.status != 'STORED':
            return result
        tokens = reply.analysis.tokens
        tree, = reply.analysis.analyses
        gold = [r[1] for r in rows]
        if [t.surface for t in tokens] != gold:
            result['alignment'] = False
            return result
        heads = [link.head for link in tree]
        for i, link in enumerate(tree):
            if link.role == 'governed' and link.head is not None and tree[link.head].role == 'preposition':
                prep = link.head
                heads[i], heads[prep] = tree[prep].head, i
        result['alignment'] = True
        result['differences'] = [[i+1, r[1], int(r[6]), (heads[i]+1 if heads[i] is not None else 0)]
                                 for i, r in enumerate(rows) if r[3] != 'PUNCT' and
                                 (heads[i] + 1 if heads[i] is not None else 0) != int(r[6])]
        result['links'] = [[t.surface, l.role, l.head] for t, l in zip(tokens, tree)]
    except TimeoutError:
        result['status'] = 'TIMEOUT'
    finally:
        signal.setitimer(signal.ITIMER_PROF, 0)
        result['probes'] = len(probes)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('corpus', type=Path)
    parser.add_argument('results', type=Path)
    parser.add_argument('--workers', type=int, default=4)
    args = parser.parse_args()
    cases = list(sentences(args.corpus))
    with Pool(args.workers) as pool:
        records = list(pool.imap(evaluate, cases, chunksize=1))
    scored = [r for r in records if r.get('alignment')]
    errors = sum(len(r['differences']) for r in scored)
    count = sum(r['words'] for r in scored)
    report = dict(sha256=hashlib.sha256(args.corpus.read_bytes()).hexdigest(), total=len(cases),
                  statuses=Counter(r['status'] for r in records), probes=sum(r['probes'] for r in records),
                  reductions=sum(r.get('reductions', 0) for r in records),
                  parsed_without_probe=sum(bool(r.get('complete')) and not r['probes']
                                           for r in records), aligned=len(scored), scored_words=count,
                  correct_heads=count-errors, corpus_words=sum(r['words'] for r in records),
                  exact_heads=sum(not r['differences'] for r in scored))
    args.results.write_text(json.dumps({'metrics': report, 'sentences': records}, ensure_ascii=False, indent=1)+'\n')
    print(json.dumps(report))


if __name__ == '__main__':
    main()
