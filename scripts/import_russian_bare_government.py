from argparse import ArgumentParser
from collections import defaultdict
from pathlib import Path
import re


CASES = {'дат': 'datv', 'род': 'gent', 'парт': 'gen2', 'твор': 'ablt'}
MACRO = re.compile(r'^\s*((?:не)?сов_инф)(_удар)?\s*\(', re.MULTILINE)
ENTRY = re.compile(r'^\s*entry\s+([а-яё-]+)\s*:\s*инфинитив\s*\{([^}]*)\}', re.MULTILINE)


def arguments(text, start):
    result = []
    depth = 0
    for index in range(start, len(text)):
        char = text[index]
        if depth == 0 and char in ',)':
            result.append(text[start:index].strip())
            if char == ')':
                return result
            start = index + 1
        elif char == '(':
            depth += 1
        elif char == ')':
            depth -= 1
    raise ValueError('Unclosed infinitive declaration')


def oblique_cases(tags):
    return {CASES[tag] for tag in re.findall('[а-яё]+', tags) if tag in CASES}


def read_infinitives(path):
    text = path.read_text(encoding='utf-8-sig').lower()
    text = re.sub(r'/\*.*?\*/|//[^\n]*', '', text, flags=re.DOTALL)
    slots = defaultdict(set)
    inherit = []
    for match in MACRO.finditer(text):
        fields = arguments(text, match.end())
        lemma = fields.pop(0)
        if match[2]:
            fields.pop(0)
        partner, tags = (fields + ['null', 'null'])[:2]
        slots[lemma].update(oblique_cases(tags))
        if match[1] == 'сов_инф' and tags == 'null' and partner != 'null':
            inherit.append((lemma, partner))
    for lemma, body in ENTRY.findall(text):
        for tags in re.findall(r'падеж\s*:\s*([а-яё,()]+)', body):
            slots[lemma].update(oblique_cases(tags))
    return slots, inherit


def build(perfective, imperfective, roles):
    perfective_slots, inherit = read_infinitives(perfective)
    imperfective_slots, _ = read_infinitives(imperfective)
    for lemma, partner in inherit:
        perfective_slots[lemma].update(imperfective_slots.get(partner, ()))
    for lemma, cases in imperfective_slots.items():
        perfective_slots[lemma].update(cases)
    for line in roles.read_text(encoding='utf-8').splitlines():
        lemma, case, _ = line.split('\t')
        if case not in CASES.values():
            raise ValueError(f'Unsupported case: {case}')
        perfective_slots[lemma].add(case)
    return ''.join(f'{lemma}\t{" ".join(sorted(cases))}\n'
                   for lemma, cases in sorted(perfective_slots.items()) if cases)


if __name__ == '__main__':
    parser = ArgumentParser()
    for name in ('perfective', 'imperfective', 'roles', 'output'):
        parser.add_argument(name, type=Path)
    args = parser.parse_args()
    args.output.write_text(build(args.perfective, args.imperfective, args.roles), encoding='utf-8')
