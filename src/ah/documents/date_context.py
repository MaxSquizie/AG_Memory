from __future__ import annotations

from dataclasses import dataclass
import re


_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


@dataclass(frozen=True, slots=True)
class DocumentDateContext:
    day: int
    month: int
    year: int | None = None

    def iso(self) -> str | None:
        if self.year is None:
            return None
        return f"{self.year:04d}-{self.month:02d}-{self.day:02d}"


_ORDINALS = {
    "первого": 1,
    "второго": 2,
    "третьего": 3,
    "четвертого": 4,
    "пятого": 5,
    "шестого": 6,
    "седьмого": 7,
    "восьмого": 8,
    "девятого": 9,
    "десятого": 10,
    "одиннадцатого": 11,
    "двенадцатого": 12,
    "тринадцатого": 13,
    "четырнадцатого": 14,
    "пятнадцатого": 15,
    "шестнадцатого": 16,
    "семнадцатого": 17,
    "восемнадцатого": 18,
    "девятнадцатого": 19,
    "двадцатого": 20,
    "двадцать первого": 21,
    "двадцать второго": 22,
    "двадцать третьего": 23,
    "двадцать четвертого": 24,
    "двадцать пятого": 25,
    "двадцать шестого": 26,
    "двадцать седьмого": 27,
    "двадцать восьмого": 28,
    "двадцать девятого": 29,
    "тридцатого": 30,
    "тридцать первого": 31,
}


def parse_document_date(line: str) -> DocumentDateContext | None:
    text = line.lower().strip()

    year_match = re.search(r"(19|20)\d\d\s+год", text)
    year = int(year_match.group(0).split()[0]) if year_match else None

    for word, day in _ORDINALS.items():
        if word in text:
            for month_name, month in _MONTHS.items():
                if month_name in text:
                    return DocumentDateContext(day, month, year)

    numeric = re.search(r"(\d{1,2})\s+([а-я]+)(?:\s+(\d{4}))?", text)
    if numeric:
        month = _MONTHS.get(numeric.group(2))
        if month:
            return DocumentDateContext(
                int(numeric.group(1)),
                month,
                int(numeric.group(3)) if numeric.group(3) else year,
            )

    return None
