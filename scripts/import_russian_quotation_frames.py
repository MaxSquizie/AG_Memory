import csv
import re
from argparse import ArgumentParser
from pathlib import Path


def extract(source):
    with source.open(encoding="utf-8") as stream:
        rows = csv.DictReader(stream, delimiter="\t", quoting=csv.QUOTE_NONE)
        return sorted({word for row in rows if "«CL»" in row["Form"]
                       for word in re.findall(r"[а-яё]+(?:-[а-яё]+)*", row["KeyLexemes"].casefold())})


if __name__ == "__main__":
    parser = ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    args.output.write_text("\n".join(extract(args.source)) + "\n", encoding="utf-8")
