from argparse import ArgumentParser
from pathlib import Path
import re


def governors(sources):
    result = set()
    for source in sources:
        for line in source.read_text(encoding='utf-8-sig').splitlines():
            entry = line.partition('//')[0].lower()
            result.update(re.findall(r'\bмодальный\(\s*([а-яё-]+)\s*\)', entry))
    return sorted(result)


if __name__ == '__main__':
    parser = ArgumentParser()
    parser.add_argument('perfective', type=Path)
    parser.add_argument('imperfective', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    args.output.write_text('\n'.join(governors((args.perfective, args.imperfective))) + '\n', encoding='utf-8')
