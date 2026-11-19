"""Build the offline government lexicon from GrammarEngine SOL and Kaikki JSONL."""
import argparse
from collections import defaultdict
from itertools import chain
import json
from pathlib import Path
import re


CASES = dict(zip('им род парт дат вин твор предл мест'.split(), 'nomn gent gen2 datv accs ablt loct loc2'.split()))
ENGLISH_CASES = dict(zip('nominative genitive partitive dative accusative instrumental prepositional locative'.split(),
                         'nomn gent gen2 datv accs ablt loct loc2'.split()))


def generate(solarix, kaikki):
    entries = defaultdict(set)
    aliases = {}
    variants = defaultdict(set)
    for line in solarix.splitlines():
        line = line.partition('//')[0].strip().lower()
        entry = re.fullmatch(r'entry (.+?)\s*:\s*предлог\s*\{\s*падеж:(.*?)\s*\}', line)
        pair = re.fullmatch(r'prep2\(\s*(.+?),\s*(.+?),\s*(.+)\)', line)
        if entry:
            names, cases = [entry[1]], entry[2]
        elif pair:
            names, cases = [pair[1], pair[2]], pair[3]
        else:
            if line.startswith('entry ') and ': предлог' in line and 'f1' not in line:
                raise ValueError(line)
            continue
        names = [re.sub(r'\s*-\s*', '-', n.strip('" ')) for n in names]
        entries[names[0]].update(CASES[tag] for tag in re.findall('[а-я]+', cases))
        for name in names:
            aliases[name] = names[0]
    for line in kaikki:
        word = json.loads(line)
        if word['lang_code'] != 'ru' or word['pos'] != 'prep':
            continue
        form = word['word'].lower()
        cases = entries[aliases.setdefault(form, form)]
        for section in [word, *word['senses']]:
            for other in section.get('alt_of', []):
                variants[aliases[form]].add(other['word'].lower().replace('\u0301', ''))
            for cat in section.get('categories', []):
                label = cat['name'].removeprefix('Russian prepositions governing the ')
                ru_case = re.fullmatch(r'Предлоги, употребляющиеся с (.+) падежом/ru', cat['name'])
                if ru_case:
                    for name in ru_case[1].split():
                        if name.startswith('именительн'):
                            cases.add('nomn')
                        elif name[:3] in CASES:
                            cases.add(CASES[name[:3]])
                        elif name.startswith('предложн'):
                            cases.add('loct')
                        elif name.startswith('творительн'):
                            cases.add('ablt')
                if label in ENGLISH_CASES:
                    cases.add(ENGLISH_CASES[label])
            for template in section.get('info_templates', []):
                if template['name'] == '+obj':
                    for tag in template.get('extra_data', {}).get('tags', []):
                        if tag in ENGLISH_CASES:
                            cases.add(ENGLISH_CASES[tag])
    changed = True
    while changed:
        changed = False
        for form, alternatives in variants.items():
            for alternative in alternatives:
                new = entries.get(aliases.get(alternative, alternative), set()) - entries[form]
                if new:
                    entries[form].update(new)
                    changed = True
    return ''.join(f'{form}\t{lemma}\t{" ".join(sorted(entries[lemma])) or "-"}\n'
                   for form, lemma in sorted(aliases.items()))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('solarix', 'kaikki_en', 'kaikki_ru', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    with args.kaikki_en.open(encoding='utf8') as en, args.kaikki_ru.open(encoding='utf8') as ru:
        args.output.write_text(generate(args.solarix.read_text(encoding='utf-8-sig'), chain(en, ru)), encoding='utf8')
