from __future__ import annotations

from pathlib import Path
from ah.core import AHCore
from ah.model import Domain
from .errors import CorpusError
from .loader import ColdCorpusWriter, CorpusImportResult, parse_actant_role


def _strip_comment(line: str) -> str:
    return line.split("--", 1)[0].strip()


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {'"', "'"}:
        return value[1:-1]
    return value


def parse_ahm_text(text: str) -> list[tuple[str, str, dict[str, str]]]:
    """Parse the small declarative subset used for cold corpus fixtures.

    Supported declarations: symbol, entity/ref, template, fact, link.
    Nested ``key = value`` rows belong to the immediately preceding declaration.
    """
    rows = text.replace("\r\n", "\n").split("\n")
    out: list[tuple[str, str, dict[str, str]]] = []
    current: tuple[str, str, dict[str, str]] | None = None
    for raw in rows:
        body = _strip_comment(raw)
        if not body:
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        if indent and current is not None and "=" in body:
            key, value = body.split("=", 1)
            current[2][key.strip().casefold()] = _unquote(value)
            continue
        words = body.split()
        head = words[0].casefold()
        if head in {"project", "module", "symbols"}:
            current = None
            continue
        if head == "import":
            out.append(("import", body[len(words[0]):].strip(), {}))
            current = None
            continue
        if head == "ref":
            rest = body[len(words[0]):].strip()
            if "=" not in rest:
                raise CorpusError(f"ref needs name = value: {body}")
            name, value = rest.split("=", 1)
            out.append(("ref", name.strip(), {"value": _unquote(value)}))
            current = None
            continue
        if head in {"symbol", "template", "fact", "link", "entity"}:
            if len(words) < 2:
                raise CorpusError(f"{head} needs a name")
            fields: dict[str, str] = {}
            if head == "template" and len(words) > 2:
                fields["predicate"] = words[2]
            out.append((head, words[1], fields))
            current = out[-1]
            continue
        raise CorpusError(f"Unsupported .ahm declaration: {body}")
    return out


def import_ahm_file(core: AHCore, path: Path, *, default_domain: Domain = Domain.C, _visited: frozenset[str] | None = None, writer: ColdCorpusWriter | None = None) -> CorpusImportResult:
    source = Path(path).expanduser().resolve()
    visited = _visited or frozenset()
    marker = str(source)
    if marker in visited:
        raise CorpusError(f"Cyclic .ahm/.prj import: {source}")
    active = writer or ColdCorpusWriter(core, domain=default_domain)
    for kind, name, fields in parse_ahm_text(source.read_text(encoding="utf-8-sig")):
        if kind == "import":
            raw = name
            if " for " in raw:
                raw = raw.split(" for ", 1)[0].strip()
            target = Path(_unquote(raw))
            if not target.is_absolute():
                target = source.parent / target
            if not target.exists() and not target.suffix:
                target = target.with_suffix(".ahm")
            import_ahm_file(core, target, default_domain=default_domain, _visited=visited | {marker}, writer=active)
        elif kind == "symbol":
            raw_forms = fields.get("forms", name).replace(",", " ").split()
            active.ensure_symbol(set(raw_forms), alias=name)
        elif kind in {"entity", "ref"}:
            active.ensure_entity(fields.get("value", fields.get("name", name)), alias=name)
        elif kind == "template":
            predicate = fields.get("predicate") or fields.get("symbol")
            if not predicate:
                raise CorpusError(f"template {name} needs predicate")
            raw_roles = fields.get("roles") or fields.get("actants") or ""
            roles = tuple(parse_actant_role(x) for x in raw_roles.replace(",", " ").split())
            active.ensure_template(predicate, roles, alias=name)
        elif kind == "fact":
            template = fields.get("template")
            predicate = fields.get("predicate") if not template else None
            actants = {parse_actant_role(k): v for k, v in fields.items() if k not in {"template", "predicate", "weight"}}
            active.add_fact(actants, predicate=predicate, template=template, weight=float(fields["weight"]) if "weight" in fields else None, alias=name)
        elif kind == "link":
            relation = fields.get("type") or fields.get("relation")
            source_name = fields.get("from") or fields.get("source")
            target_name = fields.get("to") or fields.get("target")
            if not relation or not source_name or not target_name:
                raise CorpusError(f"link {name} needs type/relation, from/source and to/target")
            active.add_link(relation, source_name, target_name, weight=float(fields["weight"]) if "weight" in fields else None, alias=name)
    return active.result
