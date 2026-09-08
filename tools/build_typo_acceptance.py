"""Build the deterministic M1 typo/noise semantic acceptance corpus.

Examples belong to acceptance data only.  Production Lexical Recovery contains no
private word/verb/example tables and never imports this module.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "acceptance_typo"


def assertion(key: str, predicate: str, **roles: str) -> dict:
    return {
        "key": key,
        "predicate": predicate,
        "status": "ASSERTED",
        "negated": False,
        "roles": roles,
    }


def corrected(raw: str, normalized: str) -> dict:
    return {
        "raw": raw,
        "status": "CORRECTED_HIGH_CONFIDENCE",
        "normalized": normalized,
    }


def protected(raw: str, *, status: str = "UNKNOWN_TOKEN") -> dict:
    return {"raw": raw, "status": status, "normalized": raw}


def exact_case(
    text: str,
    family: str,
    tags: tuple[str, ...],
    lexical: tuple[dict, ...],
    assertions: tuple[dict, ...],
) -> dict:
    return {
        "text": text,
        "grade": "EXACT",
        "family": family,
        "tags": list(tags),
        "expect": {
            "lexical_recovery": list(lexical),
            "perception": {
                "must_parse": True,
                "assertions": list(assertions),
                "queries": [],
                "relations": [],
                "conditionals": [],
            },
            "integration": {
                "must_succeed": True,
                "domains": {item["key"]: "C" for item in assertions},
            },
        },
    }


def ambiguity_case(raw: str, alternatives: tuple[str, ...]) -> dict:
    return {
        "text": raw,
        "grade": "EXACT",
        "family": "typo_ambiguous",
        "tags": ["typo", "ambiguous", "fail_closed"],
        "expect": {
            "lexical_recovery": [{
                "raw": raw,
                "status": "AMBIGUOUS",
                "normalized": None,
                "alternatives_contain": list(alternatives),
            }],
            "perception": {
                "must_parse": False,
                "assertions": [],
                "queries": [],
                "relations": [],
                "conditionals": [],
            },
            "integration": {
                "must_succeed": False,
                "safe_error_contains": "ambiguous lexical recovery",
            },
        },
    }


CASES: list[dict] = [
    # Existing adversarial frontier, retained verbatim as regression.
    exact_case("Иван купл книгу.", "typo_baseline", ("typo", "omission", "subject", "object"),
               (corrected("купл", "купил"),),
               (assertion("a1", "купить", SUBJECT="Иван", OBJECT="книга"),)),
    exact_case("Мария прочитала докмент.", "typo_baseline", ("typo", "omission", "object"),
               (corrected("докмент", "документ"),),
               (assertion("a1", "прочитать", SUBJECT="Мария", OBJECT="документ"),)),
    exact_case("Сергей передал Анне клю.", "typo_baseline", ("typo", "omission", "recipient", "object"),
               (corrected("клю", "ключ"),),
               (assertion("a1", "передать", SUBJECT="Сергей", RECIPIENT="Анна", OBJECT="ключ"),)),
    exact_case("Ольга положила книгу на стл.", "typo_baseline", ("typo", "omission", "location"),
               (corrected("стл", "стол"),),
               (assertion("a1", "положить", SUBJECT="Ольга", OBJECT="книга", LOCATION="стол"),)),
    exact_case("Пётр открл дверь ключом.", "typo_baseline", ("typo", "omission", "tool"),
               (corrected("открл", "открыл"),),
               (assertion("a1", "открыть", SUBJECT="Пётр", OBJECT="дверь", TOOL="ключ"),)),
    exact_case("Анна отправила писмо Сергею.", "typo_baseline", ("typo", "omission", "recipient"),
               (corrected("писмо", "письмо"),),
               (assertion("a1", "отправить", SUBJECT="Анна", OBJECT="письмо", RECIPIENT="Сергей"),)),
    exact_case("Мастер сделал стол из дерва.", "typo_baseline", ("typo", "omission", "material"),
               (corrected("дерва", "дерева"),),
               (assertion("a1", "сделать", SUBJECT="Мастер", OBJECT="стол", MATERIAL="дерево"),)),
    exact_case("Иван приехал в Мскву.", "typo_baseline", ("typo", "omission", "location", "proper_candidate"),
               (corrected("Мскву", "Москву"),),
               (assertion("a1", "приехать", SUBJECT="Иван", LOCATION="Москва"),)),
    exact_case("Мария работала два чса.", "typo_baseline", ("typo", "omission", "duration"),
               (corrected("чса", "часа"),),
               (assertion("a1", "работать", SUBJECT="Мария", DURATION="два часа"),)),
    exact_case("Турист остановился у рки вечером.", "typo_baseline", ("typo", "omission", "location", "time"),
               (corrected("рки", "реки"),),
               (assertion("a1", "остановиться", SUBJECT="Турист", LOCATION="река", TIME="вечером"),)),

    # Orthographic operations, word lengths, endings and semantic roles.
    exact_case("Вера закрыла окн.", "typo_edits", ("typo", "omission", "short", "object"),
               (corrected("окн", "окно"),), (assertion("a1", "закрыть", SUBJECT="Вера", OBJECT="окно"),)),
    exact_case("Вера закрыла окнно.", "typo_edits", ("typo", "extra_letter", "object"),
               (corrected("окнно", "окно"),), (assertion("a1", "закрыть", SUBJECT="Вера", OBJECT="окно"),)),
    exact_case("Вера закрыла окнп.", "typo_edits", ("typo", "keyboard_neighbor", "substitution", "object"),
               (corrected("окнп", "окно"),), (assertion("a1", "закрыть", SUBJECT="Вера", OBJECT="окно"),)),
    exact_case("Анна прчоитала отчёт.", "typo_edits", ("typo", "transposition", "predicate"),
               (corrected("прчоитала", "прочитала"),), (assertion("a1", "прочитать", SUBJECT="Анна", OBJECT="отчёт"),)),
    exact_case("Вера открыла книгп.", "typo_edits", ("typo", "keyboard_neighbor", "ending", "object"),
               (corrected("книгп", "книгу"),), (assertion("a1", "открыть", SUBJECT="Вера", OBJECT="книга"),)),
    exact_case("На столе лежали береёзы.", "typo_edits", ("typo", "yo_e", "extra_letter", "subject"),
               (corrected("береёзы", "берёзы"),), (assertion("a1", "лежать", SUBJECT="берёза", LOCATION="стол"),)),
    exact_case("Мария прочитала документт.", "typo_edits", ("typo", "extra_letter", "long", "object"),
               (corrected("документт", "документ"),), (assertion("a1", "прочитать", SUBJECT="Мария", OBJECT="документ"),)),
    exact_case("Иван работает в Москвк.", "typo_roles", ("typo", "ending", "location"),
               (corrected("Москвк", "Москве"),), (assertion("a1", "работать", SUBJECT="Иван", LOCATION="Москва"),)),
    exact_case("Анна передала пакет курьерц.", "typo_roles", ("typo", "ending", "recipient"),
               (corrected("курьерц", "курьеру"),), (assertion("a1", "передать", SUBJECT="Анна", OBJECT="пакет", RECIPIENT="курьер"),)),
    exact_case("Турист пришёл вечром.", "typo_roles", ("typo", "omission", "time"),
               (corrected("вечром", "вечером"),), (assertion("a1", "прийти", SUBJECT="Турист", TIME="вечером"),)),
    exact_case("Мария работала две минутыы.", "typo_roles", ("typo", "extra_letter", "duration", "ending"),
               (corrected("минутыы", "минуты"),), (assertion("a1", "работать", SUBJECT="Мария", DURATION="две минуты"),)),
    exact_case("Пётр ударил молоткм.", "typo_roles", ("typo", "omission", "tool", "ending"),
               (corrected("молоткм", "молотком"),), (assertion("a1", "ударить", SUBJECT="Пётр", TOOL="молоток"),)),
    exact_case("Стол покрыли дервом.", "typo_roles", ("typo", "omission", "material", "ending"),
               (corrected("дервом", "деревом"),), (assertion("a1", "покрыть", OBJECT="стол", MATERIAL="дерево"),)),
    exact_case("Отчёт проверил инжнер.", "typo_roles", ("typo", "omission", "subject", "inversion"),
               (corrected("инжнер", "инженер"),), (assertion("a1", "проверить", SUBJECT="инженер", OBJECT="отчёт"),)),
    exact_case("Инженер осмотрел электростанци.", "typo_roles", ("typo", "long", "ending", "object"),
               (corrected("электростанци", "электростанцию"),), (assertion("a1", "осмотреть", SUBJECT="Инженер", OBJECT="электростанция"),)),
    exact_case("Анна заварила члй.", "typo_edits", ("typo", "substitution", "short", "object"),
               (corrected("члй", "чай"),), (assertion("a1", "заварить", SUBJECT="Анна", OBJECT="чай"),)),
    exact_case("Сотрудник открыл архивп.", "typo_edits", ("typo", "extra_letter", "object"),
               (corrected("архивп", "архив"),), (assertion("a1", "открыть", SUBJECT="Сотрудник", OBJECT="архив"),)),
    exact_case("Мария купила журнла.", "typo_edits", ("typo", "transposition", "object"),
               (corrected("журнла", "журнал"),), (assertion("a1", "купить", SUBJECT="Мария", OBJECT="журнал"),)),
    exact_case("Анна проверрила отчёт.", "typo_edits", ("typo", "extra_letter", "predicate"),
               (corrected("проверрила", "проверила"),), (assertion("a1", "проверить", SUBJECT="Анна", OBJECT="отчёт"),)),
    exact_case("Анна отпраила письмо.", "typo_edits", ("typo", "omission", "predicate"),
               (corrected("отпраила", "отправила"),), (assertion("a1", "отправить", SUBJECT="Анна", OBJECT="письмо"),)),
    exact_case("Мария полочила письмо.", "typo_edits", ("typo", "substitution", "predicate"),
               (corrected("полочила", "получила"),), (assertion("a1", "получить", SUBJECT="Мария", OBJECT="письмо"),)),
    exact_case("Иван живёт у станци.", "typo_roles", ("typo", "ending", "location"),
               (corrected("станци", "станции"),), (assertion("a1", "жить", SUBJECT="Иван", LOCATION="станция"),)),
    exact_case("Курьер приехал со склда.", "typo_roles", ("typo", "omission", "source"),
               (corrected("склда", "склада"),), (assertion("a1", "приехать", SUBJECT="Курьер", SOURCE="склад"),)),
    exact_case("Анна передала отчёт мастреу.", "typo_roles", ("typo", "transposition", "recipient"),
               (corrected("мастреу", "мастеру"),), (assertion("a1", "передать", SUBJECT="Анна", OBJECT="отчёт", RECIPIENT="мастер"),)),
    exact_case("Пётр открыл дверь ключм.", "typo_roles", ("typo", "omission", "tool"),
               (corrected("ключм", "ключом"),), (assertion("a1", "открыть", SUBJECT="Пётр", OBJECT="дверь", TOOL="ключ"),)),
    exact_case("Иван купил кнгу.", "typo_edits", ("typo", "omission", "object", "short"),
               (corrected("кнгу", "книгу"),), (assertion("a1", "купить", SUBJECT="Иван", OBJECT="книга"),)),
    exact_case("Пётр открыл дврь.", "typo_edits", ("typo", "omission", "object"),
               (corrected("дврь", "дверь"),), (assertion("a1", "открыть", SUBJECT="Пётр", OBJECT="дверь"),)),

    # Typo + inversion: semantic roles are specified independently of order.
    exact_case("Книгу прочитал инжнер.", "typo_inversion", ("typo", "inversion", "subject"),
               (corrected("инжнер", "инженер"),), (assertion("a1", "прочитать", SUBJECT="инженер", OBJECT="книга"),)),
    exact_case("Вчера документт Мария прочитала.", "typo_inversion", ("typo", "inversion", "object", "time"),
               (corrected("документт", "документ"),), (assertion("a1", "прочитать", SUBJECT="Мария", OBJECT="документ", TIME="вчера"),)),
    exact_case("Анне клю Сергей передал.", "typo_inversion", ("typo", "inversion", "recipient", "object"),
               (corrected("клю", "ключ"),), (assertion("a1", "передать", SUBJECT="Сергей", RECIPIENT="Анна", OBJECT="ключ"),)),
    exact_case("На стл книгу Ольга положила.", "typo_inversion", ("typo", "inversion", "location"),
               (corrected("стл", "стол"),), (assertion("a1", "положить", SUBJECT="Ольга", OBJECT="книга", LOCATION="стол"),)),
    exact_case("Ключом дврь Пётр открыл.", "typo_inversion", ("typo", "inversion", "tool", "object"),
               (corrected("дврь", "дверь"),), (assertion("a1", "открыть", SUBJECT="Пётр", OBJECT="дверь", TOOL="ключ"),)),
    exact_case("В Мскву Иван приехал.", "typo_inversion", ("typo", "inversion", "location"),
               (corrected("Мскву", "Москву"),), (assertion("a1", "приехать", SUBJECT="Иван", LOCATION="Москва"),)),
    exact_case("У реки вечром турист остановился.", "typo_inversion", ("typo", "inversion", "time", "location"),
               (corrected("вечром", "вечером"),), (assertion("a1", "остановиться", SUBJECT="турист", TIME="вечером", LOCATION="река"),)),
    exact_case("Два чса Мария работала.", "typo_inversion", ("typo", "inversion", "duration"),
               (corrected("чса", "часа"),), (assertion("a1", "работать", SUBJECT="Мария", DURATION="два часа"),)),
    exact_case("Из дерва мастер сделал стол.", "typo_inversion", ("typo", "inversion", "material"),
               (corrected("дерва", "дерева"),), (assertion("a1", "сделать", SUBJECT="мастер", OBJECT="стол", MATERIAL="дерево"),)),
    exact_case("Со склда курьер принёс пакет.", "typo_inversion", ("typo", "inversion", "source"),
               (corrected("склда", "склада"),), (assertion("a1", "принести", SUBJECT="курьер", OBJECT="пакет", SOURCE="склад"),)),
    exact_case("Письмо Сергею отпраила Анна.", "typo_inversion", ("typo", "inversion", "recipient", "predicate"),
               (corrected("отпраила", "отправила"),), (assertion("a1", "отправить", SUBJECT="Анна", OBJECT="письмо", RECIPIENT="Сергей"),)),
    exact_case("Отвёрткой окн открыл Пётр.", "typo_inversion", ("typo", "inversion", "tool", "object"),
               (corrected("окн", "окно"),), (assertion("a1", "открыть", SUBJECT="Пётр", OBJECT="окно", TOOL="отвёртка"),)),

    # Typo + ellipsis. The recovered frame, not word order, owns role inheritance.
    exact_case("Иван купил кнгу, а Мария — журнал.", "typo_ellipsis", ("typo", "ellipsis", "object"),
               (corrected("кнгу", "книгу"),),
               (assertion("a1", "купить", SUBJECT="Иван", OBJECT="книга"), assertion("a2", "купить", SUBJECT="Мария", OBJECT="журнал"))),
    exact_case("Иван купл чай, а Мария — кофе.", "typo_ellipsis", ("typo", "ellipsis", "predicate"),
               (corrected("купл", "купил"),),
               (assertion("a1", "купить", SUBJECT="Иван", OBJECT="чай"), assertion("a2", "купить", SUBJECT="Мария", OBJECT="кофе"))),
    exact_case("Анна положила книгу на стл, а Мария — журнал на полку.", "typo_ellipsis", ("typo", "ellipsis", "location"),
               (corrected("стл", "стол"),),
               (assertion("a1", "положить", SUBJECT="Анна", OBJECT="книга", LOCATION="стол"), assertion("a2", "положить", SUBJECT="Мария", OBJECT="журнал", LOCATION="полка"))),
    exact_case("Сергей передал Анне клю, а Пётр — Вере письмо.", "typo_ellipsis", ("typo", "ellipsis", "recipient", "object"),
               (corrected("клю", "ключ"),),
               (assertion("a1", "передать", SUBJECT="Сергей", RECIPIENT="Анна", OBJECT="ключ"), assertion("a2", "передать", SUBJECT="Пётр", RECIPIENT="Вера", OBJECT="письмо"))),
    exact_case("Мария работала два чса, а Анна — три часа.", "typo_ellipsis", ("typo", "ellipsis", "duration"),
               (corrected("чса", "часа"),),
               (assertion("a1", "работать", SUBJECT="Мария", DURATION="два часа"), assertion("a2", "работать", SUBJECT="Анна", DURATION="три часа"))),
    exact_case("Иван приехал в Мскву, а Пётр — в Казань.", "typo_ellipsis", ("typo", "ellipsis", "location"),
               (corrected("Мскву", "Москву"),),
               (assertion("a1", "приехать", SUBJECT="Иван", LOCATION="Москва"), assertion("a2", "приехать", SUBJECT="Пётр", LOCATION="Казань"))),
    exact_case("Мастер открл дверь ключом, а ученик — окно отвёрткой.", "typo_ellipsis", ("typo", "ellipsis", "predicate", "tool"),
               (corrected("открл", "открыл"),),
               (assertion("a1", "открыть", SUBJECT="Мастер", OBJECT="дверь", TOOL="ключ"), assertion("a2", "открыть", SUBJECT="ученик", OBJECT="окно", TOOL="отвёртка"))),
    exact_case("Анна отпраила письмо Сергею, а Вера — отчёт Петру.", "typo_ellipsis", ("typo", "ellipsis", "predicate", "recipient"),
               (corrected("отпраила", "отправила"),),
               (assertion("a1", "отправить", SUBJECT="Анна", OBJECT="письмо", RECIPIENT="Сергей"), assertion("a2", "отправить", SUBJECT="Вера", OBJECT="отчёт", RECIPIENT="Пётр"))),
    exact_case("Книгу прочитала Мария, а докмент — Анна.", "typo_ellipsis", ("typo", "ellipsis", "inversion", "object"),
               (corrected("докмент", "документ"),),
               (assertion("a1", "прочитать", SUBJECT="Мария", OBJECT="книга"), assertion("a2", "прочитать", SUBJECT="Анна", OBJECT="документ"))),
    exact_case("На стл книгу положила Ольга, а на полку журнал — Вера.", "typo_ellipsis", ("typo", "ellipsis", "inversion", "location"),
               (corrected("стл", "стол"),),
               (assertion("a1", "положить", SUBJECT="Ольга", OBJECT="книга", LOCATION="стол"), assertion("a2", "положить", SUBJECT="Вера", OBJECT="журнал", LOCATION="полка"))),

    # Several independent OOV errors in one utterance.
    exact_case("Вчера инжнер прочитал докмент.", "typo_multiple", ("typo", "multiple_errors", "subject", "object", "time"),
               (corrected("инжнер", "инженер"), corrected("докмент", "документ")),
               (assertion("a1", "прочитать", SUBJECT="инженер", OBJECT="документ", TIME="вчера"),)),
    exact_case("Пётр открл дврь ключм.", "typo_multiple", ("typo", "multiple_errors", "predicate", "object", "tool"),
               (corrected("открл", "открыл"), corrected("дврь", "дверь"), corrected("ключм", "ключом")),
               (assertion("a1", "открыть", SUBJECT="Пётр", OBJECT="дверь", TOOL="ключ"),)),
    exact_case("Анна отпраила писмо Сергею.", "typo_multiple", ("typo", "multiple_errors", "predicate", "object", "recipient"),
               (corrected("отпраила", "отправила"), corrected("писмо", "письмо")),
               (assertion("a1", "отправить", SUBJECT="Анна", OBJECT="письмо", RECIPIENT="Сергей"),)),
    exact_case("Турист вечром остановился у рки.", "typo_multiple", ("typo", "multiple_errors", "time", "location"),
               (corrected("вечром", "вечером"), corrected("рки", "реки")),
               (assertion("a1", "остановиться", SUBJECT="Турист", TIME="вечером", LOCATION="река"),)),
    exact_case("Мастер сделал стл из дерва.", "typo_multiple", ("typo", "multiple_errors", "object", "material"),
               (corrected("стл", "стол"), corrected("дерва", "дерева")),
               (assertion("a1", "сделать", SUBJECT="Мастер", OBJECT="стол", MATERIAL="дерево"),)),
    exact_case("Курьер принс пакетт со склда.", "typo_multiple", ("typo", "multiple_errors", "predicate", "object", "source"),
               (corrected("принс", "принёс"), corrected("пакетт", "пакет"), corrected("склда", "склада")),
               (assertion("a1", "принести", SUBJECT="Курьер", OBJECT="пакет", SOURCE="склад"),)),
    exact_case("Мария работла два чса в офисе.", "typo_multiple", ("typo", "multiple_errors", "predicate", "duration", "location"),
               (corrected("работла", "работала"), corrected("чса", "часа")),
               (assertion("a1", "работать", SUBJECT="Мария", DURATION="два часа", LOCATION="офис"),)),
    exact_case("В Мскве инжнер проверил докмент.", "typo_multiple", ("typo", "multiple_errors", "inversion", "location", "subject", "object"),
               (corrected("Мскве", "Москве"), corrected("инжнер", "инженер"), corrected("докмент", "документ")),
               (assertion("a1", "проверить", SUBJECT="инженер", OBJECT="документ", LOCATION="Москва"),)),

    # Negative cases: unknown/rare/technical forms must survive unchanged.
    exact_case("Ксентарий приехал в Москву.", "typo_negative_oov", ("negative", "name", "unknown_token"),
               (protected("Ксентарий"),), (assertion("a1", "приехать", SUBJECT="Ксентарий", LOCATION="Москва"),)),
    exact_case("РКТ передал сигнал.", "typo_negative_oov", ("negative", "acronym", "unknown_token"),
               (protected("РКТ"),), (assertion("a1", "передать", SUBJECT="РКТ", OBJECT="сигнал"),)),
    exact_case("Модуль обрабатывает «кванторий».", "typo_negative_oov", ("negative", "term", "quoted", "unknown_token"),
               (protected("кванторий"),), (assertion("a1", "обрабатывать", SUBJECT="Модуль", OBJECT="кванторий"),)),
    exact_case("Модуль использует QX17.", "typo_negative_oov", ("negative", "code", "alphanumeric", "unknown_token"),
               (protected("QX17"),), (assertion("a1", "использовать", SUBJECT="Модуль", OBJECT="QX17"),)),
    exact_case("Нейросфера анализирует сигнал.", "typo_negative_oov", ("negative", "neologism", "name", "unknown_token"),
               (protected("Нейросфера"),), (assertion("a1", "анализировать", SUBJECT="Нейросфера", OBJECT="сигнал"),)),
    exact_case("Система использует ZETA9.", "typo_negative_oov", ("negative", "term", "latin", "unknown_token"),
               (protected("ZETA9"),), (assertion("a1", "использовать", SUBJECT="Система", OBJECT="ZETA9"),)),
    exact_case("Орнитолог увидел выпь.", "typo_negative_oov", ("negative", "rare_word", "exact"),
               (protected("выпь", status="EXACT"),), (assertion("a1", "увидеть", SUBJECT="Орнитолог", OBJECT="выпь"),)),
    exact_case("Петр увидел елку.", "typo_negative_oov", ("negative", "yo_e", "exact"),
               (protected("Петр", status="EXACT"), protected("елку", status="EXACT")),
               (assertion("a1", "увидеть", SUBJECT="Пётр", OBJECT="ёлка"),)),

    # Context-free OOV fragments with several valid dictionary neighbours.  No
    # semantic reranker has evidence to choose, so the safe exact result is ERROR.
    ambiguity_case("ктт", ("кот", "кит")),
    ambiguity_case("плн", ("план", "плен")),
    ambiguity_case("стл", ("стал", "стыл")),
    ambiguity_case("лкк", ("лук", "лак")),
    ambiguity_case("клю", ("клюй", "колю")),
    ambiguity_case("писмо", ("пасмо", "письмо")),
]


def main() -> None:
    if len(CASES) != 81:
        raise RuntimeError(f"Expected 81 typo acceptance cases, got {len(CASES)}")
    texts = [item["text"] for item in CASES]
    if len(set(texts)) != len(texts):
        raise RuntimeError("Typo acceptance texts must be unique")
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "cases.txt").write_text("\n".join(texts) + "\n", encoding="utf-8")
    payload = {"version": 1, "cases": []}
    for index, item in enumerate(CASES, start=1):
        enriched = dict(item)
        enriched["scenario"] = f"m1_typo_{index:03d}"
        payload["cases"].append(enriched)
    (OUT / "oracle.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    (OUT / "README.md").write_text(
        "# M1 typo/noise acceptance\n\n"
        "81 scenario-isolated cases for Lexical Recovery before semantic formalization. "
        "The suite covers all four edit operations, keyboard neighbours, ё/е, inflection, "
        "short/long words, semantic roles, inversion, ellipsis, multiple errors, protected "
        "names/terms/acronyms/codes, rare exact words, and fail-closed ambiguity.\n\n"
        "Run through the GUI button `M1: typo/noise acceptance` or pass these cases/oracle "
        "to `semantic-acceptance`.\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
