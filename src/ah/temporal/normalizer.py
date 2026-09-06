from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re

from .contracts import (
    TemporalAnchorContext,
    TemporalCandidate,
    TemporalKind,
    TemporalPrecision,
    TemporalValue,
)


_RU_MONTHS = {
    "январь": 1, "января": 1, "январе": 1,
    "февраль": 2, "февраля": 2, "феврале": 2,
    "март": 3, "марта": 3, "марте": 3,
    "апрель": 4, "апреля": 4, "апреле": 4,
    "май": 5, "мая": 5,
    "июнь": 6, "июня": 6, "июне": 6,
    "июль": 7, "июля": 7, "июле": 7,
    "август": 8, "августа": 8, "августе": 8,
    "сентябрь": 9, "сентября": 9, "сентябре": 9,
    "октябрь": 10, "октября": 10, "октябре": 10,
    "ноябрь": 11, "ноября": 11, "ноябре": 11,
    "декабрь": 12, "декабря": 12, "декабре": 12,
}

_RELATIVE_DAY = {
    "сегодня": 0,
    "вчера": -1,
    "завтра": 1,
}

_RELATIVE_MARKERS = {
    "сегодня", "вчера", "завтра", "сейчас", "ныне",
    "позавчера", "послезавтра", "прошлой неделе", "прошлую неделю",
    "следующей неделе", "следующую неделю", "этой неделе", "эту неделю",
}


@dataclass(frozen=True, slots=True)
class _ParsedPoint:
    value: str
    precision: TemporalPrecision
    timezone: str | None = None


class TemporalNormalizer:
    """Deterministic source-time normalizer.

    It recognizes only structures whose temporal value can be recovered without a
    semantic guess. Unknown ordinary TIME phrases are left untouched; explicitly
    relative phrases are marked unresolved when no admissible anchor exists.
    """

    _ISO_DATETIME = re.compile(
        r"^(?P<date>\d{4}-\d{2}-\d{2})[T ](?P<h>\d{1,2}):(?P<m>\d{2})"
        r"(?::(?P<s>\d{2}))?(?P<tz>Z|[+-]\d{2}:?\d{2})?$"
    )
    _ISO_DATE = re.compile(r"^(?P<y>\d{4})-(?P<mo>\d{1,2})-(?P<d>\d{1,2})$")
    _DOT_DATE = re.compile(r"^(?P<d>\d{1,2})[./](?P<mo>\d{1,2})[./](?P<y>\d{4})$")
    _YEAR_MONTH = re.compile(r"^(?P<y>\d{4})-(?P<mo>\d{1,2})$")
    _YEAR = re.compile(r"^(?P<y>\d{4})\s*(?:г\.?|года?)?$")
    _TIME = re.compile(r"^(?:в\s+)?(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?$")
    _DAY_MONTH_YEAR = re.compile(
        r"^(?P<d>\d{1,2})\s+(?P<month>[а-яё]+)\s+(?P<y>\d{4})(?:\s*г(?:ода)?\.?)?$",
        re.IGNORECASE,
    )
    _MONTH_YEAR = re.compile(
        r"^(?:в\s+)?(?P<month>[а-яё]+)\s+(?P<y>\d{4})(?:\s*г(?:оду)?\.?)?$",
        re.IGNORECASE,
    )
    _BARE_MONTH = re.compile(r"^(?:в\s+)?(?P<month>[а-яё]+)$", re.IGNORECASE)
    _RELATIVE_WITH_TIME = re.compile(
        r"^(?P<rel>сегодня|вчера|завтра)\s+(?:в\s+)?(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?$",
        re.IGNORECASE,
    )
    _INTERVAL = re.compile(
        r"^(?:с|от)\s+(?P<left>.+?)\s+(?:по|до)\s+(?P<right>.+)$",
        re.IGNORECASE,
    )

    @staticmethod
    def _tz_text(dt: datetime) -> str | None:
        offset = dt.utcoffset()
        if offset is None:
            return None
        seconds = int(offset.total_seconds())
        sign = "+" if seconds >= 0 else "-"
        seconds = abs(seconds)
        hours, rem = divmod(seconds, 3600)
        minutes = rem // 60
        return f"{sign}{hours:02d}:{minutes:02d}"

    @staticmethod
    def _validate_date(year: int, month: int, day: int) -> None:
        datetime(year, month, day)

    @staticmethod
    def _validate_time(hour: int, minute: int, second: int = 0) -> None:
        if not 0 <= hour <= 23 or not 0 <= minute <= 59 or not 0 <= second <= 59:
            raise ValueError("Invalid time-of-day")

    @staticmethod
    def _normalize_tz(raw: str | None) -> str | None:
        if raw is None:
            return None
        if raw == "Z":
            return "+00:00"
        if len(raw) == 5 and raw[3] != ":":
            return raw[:3] + ":" + raw[3:]
        return raw

    def _parse_point(self, text: str) -> _ParsedPoint | None:
        value = " ".join(text.strip().split())
        folded = value.casefold().replace("ё", "е")

        match = self._ISO_DATETIME.fullmatch(value)
        if match:
            y, mo, d = (int(part) for part in match.group("date").split("-"))
            h = int(match.group("h")); minute = int(match.group("m")); sec = int(match.group("s") or 0)
            self._validate_date(y, mo, d); self._validate_time(h, minute, sec)
            precision = TemporalPrecision.SECOND if match.group("s") is not None else TemporalPrecision.MINUTE
            suffix = f":{sec:02d}" if precision is TemporalPrecision.SECOND else ""
            tz = self._normalize_tz(match.group("tz"))
            tz_suffix = tz or ""
            return _ParsedPoint(f"{y:04d}-{mo:02d}-{d:02d}T{h:02d}:{minute:02d}{suffix}{tz_suffix}", precision, tz)

        match = self._ISO_DATE.fullmatch(value)
        if match:
            y = int(match.group("y")); mo = int(match.group("mo")); d = int(match.group("d"))
            self._validate_date(y, mo, d)
            return _ParsedPoint(f"{y:04d}-{mo:02d}-{d:02d}", TemporalPrecision.DAY)

        match = self._DOT_DATE.fullmatch(value)
        if match:
            y = int(match.group("y")); mo = int(match.group("mo")); d = int(match.group("d"))
            self._validate_date(y, mo, d)
            return _ParsedPoint(f"{y:04d}-{mo:02d}-{d:02d}", TemporalPrecision.DAY)

        match = self._DAY_MONTH_YEAR.fullmatch(folded)
        if match:
            month = _RU_MONTHS.get(match.group("month"))
            if month is not None:
                year = int(match.group("y")); day = int(match.group("d"))
                self._validate_date(year, month, day)
                return _ParsedPoint(f"{year:04d}-{month:02d}-{day:02d}", TemporalPrecision.DAY)

        match = self._YEAR_MONTH.fullmatch(value)
        if match:
            year = int(match.group("y")); month = int(match.group("mo"))
            if not 1 <= month <= 12:
                raise ValueError("Invalid month")
            return _ParsedPoint(f"{year:04d}-{month:02d}", TemporalPrecision.MONTH)

        match = self._MONTH_YEAR.fullmatch(folded)
        if match:
            month = _RU_MONTHS.get(match.group("month"))
            if month is not None:
                return _ParsedPoint(f"{int(match.group('y')):04d}-{month:02d}", TemporalPrecision.MONTH)

        match = self._YEAR.fullmatch(folded)
        if match:
            return _ParsedPoint(f"{int(match.group('y')):04d}", TemporalPrecision.YEAR)

        match = self._TIME.fullmatch(folded)
        if match:
            h = int(match.group("h")); minute = int(match.group("m")); sec_raw = match.group("s")
            sec = int(sec_raw or 0)
            self._validate_time(h, minute, sec)
            precision = TemporalPrecision.SECOND if sec_raw is not None else TemporalPrecision.MINUTE
            suffix = f":{sec:02d}" if precision is TemporalPrecision.SECOND else ""
            return _ParsedPoint(f"T{h:02d}:{minute:02d}{suffix}", precision)

        match = self._BARE_MONTH.fullmatch(folded)
        if match:
            month = _RU_MONTHS.get(match.group("month"))
            if month is not None:
                return _ParsedPoint(f"--{month:02d}", TemporalPrecision.MONTH)
        return None

    def normalize(
        self,
        text: str,
        anchors: TemporalAnchorContext | None = None,
    ) -> TemporalCandidate | None:
        raw = " ".join(text.strip().split())
        if not raw:
            return None
        folded = raw.casefold().replace("ё", "е")
        anchors = anchors or TemporalAnchorContext()

        match = self._INTERVAL.fullmatch(raw)
        if match:
            left = self._parse_point(match.group("left"))
            right = self._parse_point(match.group("right"))
            if left is not None and right is not None:
                precision = left.precision if left.precision == right.precision else TemporalPrecision.UNKNOWN
                tz = left.timezone if left.timezone == right.timezone else None
                return TemporalCandidate(
                    TemporalValue(
                        TemporalKind.INTERVAL,
                        left.value,
                        right.value,
                        precision,
                        tz,
                        source_text=raw,
                    )
                )

        match = self._RELATIVE_WITH_TIME.fullmatch(folded)
        if match:
            anchor = anchors.preferred()
            if anchor is None:
                return TemporalCandidate(None, relative=True, unresolved_reason="relative time has no anchor")
            day = anchor + timedelta(days=_RELATIVE_DAY[match.group("rel")])
            h = int(match.group("h")); minute = int(match.group("m")); sec_raw = match.group("s")
            sec = int(sec_raw or 0)
            self._validate_time(h, minute, sec)
            resolved = day.replace(hour=h, minute=minute, second=sec, microsecond=0)
            precision = TemporalPrecision.SECOND if sec_raw is not None else TemporalPrecision.MINUTE
            rendered = resolved.isoformat(timespec="seconds" if precision is TemporalPrecision.SECOND else "minutes")
            return TemporalCandidate(
                TemporalValue(
                    TemporalKind.POINT, rendered, None, precision,
                    self._tz_text(resolved), source_text=raw,
                ),
                relative=True,
            )

        if folded in _RELATIVE_DAY or folded in {"сейчас", "ныне"}:
            anchor = anchors.preferred()
            if anchor is None:
                return TemporalCandidate(None, relative=True, unresolved_reason="relative time has no anchor")
            resolved = anchor if folded in {"сейчас", "ныне"} else anchor + timedelta(days=_RELATIVE_DAY[folded])
            if folded in {"сейчас", "ныне"}:
                rendered = resolved.replace(microsecond=0).isoformat(timespec="seconds")
                precision = TemporalPrecision.SECOND
            else:
                rendered = resolved.date().isoformat()
                precision = TemporalPrecision.DAY
            return TemporalCandidate(
                TemporalValue(
                    TemporalKind.POINT,
                    rendered,
                    None,
                    precision,
                    self._tz_text(resolved),
                    source_text=raw,
                ),
                relative=True,
            )

        point = self._parse_point(raw)
        if point is not None:
            return TemporalCandidate(
                TemporalValue(
                    TemporalKind.POINT,
                    point.value,
                    None,
                    point.precision,
                    point.timezone,
                    source_text=raw,
                )
            )

        # Fail closed only for phrases that explicitly require a moving anchor.
        # Unknown temporal nouns ("утром", "на праздники") remain available to
        # ordinary semantic parsing rather than being guessed here.
        if any(marker in folded for marker in _RELATIVE_MARKERS):
            return TemporalCandidate(None, relative=True, unresolved_reason="relative temporal phrase is not deterministically resolvable")
        return None
