from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ah.core import AHCore
from ah.model import Domain

from .errors import CorpusError
from .loader import ColdCorpusWriter, CorpusImportResult, parse_actant_role, parse_section_domain


@dataclass(frozen=True, slots=True)
class AhmImport:
    path: str
    section: str


@dataclass(frozen=True, slots=True)
class AhmItem:
    kind: str
    name: str
    fields: dict[str, str]
    args: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AhmModule:
    kind: str
    name: str
    items: tuple[AhmItem, ...]


@dataclass(frozen=True, slots=True)
class AhmDocument:
    imports: tuple[AhmImport, ...]
    modules: tuple[AhmModule, ...]


def _strip_comment(line: str) -> str:
    in_quotes = False
    quote = ""
    out: list[str] = []
    index = 0
    while index < len(line):
        ch = line[index]
        if in_quotes:
            out.append(ch)
            if ch == quote:
                in_quotes = False
            elif ch == "\\" and index + 1 < len(line):
                out.append(line[index + 1])
                index += 1
            index += 1
            continue
        if ch in {'"', "'"}:
            in_quotes = True
            quote = ch
            out.append(ch)
            index += 1
            continue
        if line.startswith("--", index):
            break
        out.append(ch)
        index += 1
    return "".join(out)


def _unquote(raw: str) -> str:
    text = raw.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        return text[1:-1]
    return text


def _split_words(raw: str) -> tuple[str, ...]:
    text = raw.replace(",", " ").strip()
    if not text:
        return ()
    return tuple(part for part in text.split() if part)


def parse_ahm_text(text: str) -> AhmDocument:
    rows: list[tuple[int, str]] = []
    for line in text.splitlines():
        indent = len(line) - len(line.lstrip(" "))
        body = _strip_comment(line).strip()
        if body:
            rows.append((indent, body))

    imports: list[AhmImport] = []
    modules: list[AhmModule] = []
    index = 0

    def peek() -> tuple[int, str] | None:
        return rows[index] if index < len(rows) else None

    def parse_fields(parent_indent: int) -> dict[str, str]:
        nonlocal index
        fields: dict[str, str] = {}
        while True:
            nxt = peek()
            if nxt is None or nxt[0] <= parent_indent:
                break
            _, body = nxt
            index += 1
            if "=" not in body:
                raise CorpusError(f"Expected field assignment, got: {body}")
            key, value = body.split("=", 1)
            fields[key.strip().casefold()] = _unquote(value)
        return fields

    def parse_item(indent: int, body: str) -> AhmItem:
        parts = body.split()
        kind = parts[0].casefold()
        if kind == "ref":
            rest = body[len(parts[0]) :].strip()
            if "=" not in rest:
                raise CorpusError(f"ref needs name = value: {body}")
            name, value = rest.split("=", 1)
            if peek() is not None and peek()[0] > indent:
                raise CorpusError("ref does not take nested fields")
            return AhmItem("ref", name.strip(), {"value": _unquote(value)}, ())
        if kind in {"image", "symbol", "template", "fact", "link"}:
            name = parts[1] if len(parts) > 1 else ""
            args = tuple(parts[2:])
            if not name:
                raise CorpusError(f"{kind} needs a name")
            return AhmItem(kind, name, parse_fields(indent), args)
        if kind in {"func", "group"}:
            raise CorpusError(f"{kind} is outside the MVP .ahm subset (symbols/fact/link)")
        raise CorpusError(f"Unsupported .ahm declaration: {body}")

    current_kind: str | None = None
    current_name = ""
    current_items: list[AhmItem] = []

    def flush_module() -> None:
        nonlocal current_kind, current_name, current_items
        if current_kind is None:
            return
        modules.append(AhmModule(current_kind, current_name, tuple(current_items)))
        current_kind = None
        current_name = ""
        current_items = []

    while True:
        nxt = peek()
        if nxt is None:
            break
        indent, body = nxt
        index += 1
        parts = body.split()
        head = parts[0].casefold()
        if head == "project":
            flush_module()
            while True:
                child = peek()
                if child is None or child[0] <= indent:
                    break
                child_indent, child_body = child
                index += 1
                words = child_body.split()
                if words and words[0].casefold() == "import":
                    if "for" not in [w.casefold() for w in words]:
                        raise CorpusError(f"import needs 'for <section>': {child_body}")
                    for_at = next(i for i, w in enumerate(words) if w.casefold() == "for")
                    path = " ".join(words[1:for_at])
                    section = " ".join(words[for_at + 1 :])
                    imports.append(AhmImport(_unquote(path), section.strip()))
                    continue
                if words and words[0].casefold() == "sensor":
                    parse_fields(child_indent)
                    continue
                raise CorpusError(f"Unsupported .prj declaration: {child_body}")
            continue
        if head in {"symbols", "module"}:
            flush_module()
            current_kind = head
            current_name = parts[1] if len(parts) > 1 else head
            continue
        if head in {"image", "symbol", "template", "fact", "link", "ref"}:
            if current_kind is None:
                current_kind = "module"
                current_name = "Facts"
            current_items.append(parse_item(indent, body))
            continue
        raise CorpusError(
            "Expected 'project', 'symbols', 'module', or a declaration, "
            f"got: {body}"
        )

    flush_module()
    return AhmDocument(tuple(imports), tuple(modules))


def _resolve_import_path(base: Path, raw: str) -> Path:
    candidate = Path(raw)
    if not candidate.is_absolute():
        candidate = base / raw
    if candidate.is_file():
        return candidate
    if candidate.suffix.lower() != ".ahm":
        with_suffix = candidate.with_suffix(".ahm")
        if with_suffix.is_file():
            return with_suffix
    raise CorpusError(f"Cannot find imported .ahm file: {raw}")


def _apply_module(writer: ColdCorpusWriter, module: AhmModule) -> None:
    if module.kind == "symbols":
        allowed = {"image", "symbol"}
        unexpected = {item.kind for item in module.items if item.kind not in allowed}
        if unexpected:
            raise CorpusError(
                f"symbols module {module.name!r} may only contain image/symbol, not {sorted(unexpected)}"
            )
    for item in module.items:
        if item.kind == "image":
            data = item.fields.get("data")
            if not data:
                raise CorpusError(f"image {item.name} needs data=")
            writer.record_image(item.name, data)
            continue
        if item.kind == "symbol":
            forms: set[str] = set()
            raw_images = item.fields.get("images", "")
            for image_name in _split_words(raw_images):
                if image_name not in writer.image_data:
                    raise CorpusError(f"symbol {item.name} references unknown image {image_name}")
                forms.add(writer.image_data[image_name])
            if "forms" in item.fields:
                forms.update(_split_words(item.fields["forms"]))
            if not forms:
                forms.add(item.name)
            writer.ensure_symbol(forms, alias=item.name)
            continue
        if item.kind == "ref":
            writer.ensure_entity(item.fields["value"], alias=item.name)
            continue
        if item.kind == "template":
            predicate = item.args[0] if item.args else item.fields.get("predicate")
            if not predicate:
                raise CorpusError(f"template {item.name} needs a predicate symbol")
            raw_roles = item.fields.get("actants") or item.fields.get("roles") or ""
            roles = tuple(parse_actant_role(part) for part in _split_words(raw_roles))
            writer.ensure_template(predicate, roles, alias=item.name)
            continue
        if item.kind == "fact":
            template = item.args[0] if item.args else item.fields.get("template")
            actants = {
                parse_actant_role(key): value
                for key, value in item.fields.items()
                if key not in {"template", "weight", "predicate"}
            }
            writer.add_fact(
                actants,
                template=template,
                predicate=None if template else item.fields.get("predicate"),
                weight=float(item.fields["weight"]) if "weight" in item.fields else None,
                alias=item.name,
            )
            continue
        if item.kind == "link":
            relation = item.fields.get("type") or item.fields.get("relation")
            source = item.fields.get("from") or item.fields.get("source")
            target = item.fields.get("to") or item.fields.get("target")
            if not relation or not source or not target:
                raise CorpusError(f"link {item.name} needs type, from, and to")
            writer.add_link(
                relation,
                source,
                target,
                weight=float(item.fields["weight"]) if "weight" in item.fields else None,
                alias=item.name,
            )


def import_ahm_file(
    core: AHCore,
    path: Path,
    *,
    default_domain: Domain = Domain.C,
    _visited: frozenset[str] | None = None,
    writer: ColdCorpusWriter | None = None,
) -> CorpusImportResult:
    source = path.expanduser().resolve()
    visited = _visited or frozenset()
    marker = str(source)
    if marker in visited:
        raise CorpusError(f"Cyclic .prj import: {source}")
    document = parse_ahm_text(source.read_text(encoding="utf-8"))
    active = writer or ColdCorpusWriter(core, domain=default_domain)
    if document.imports:
        for spec in document.imports:
            imported = _resolve_import_path(source.parent, spec.path)
            section_domain = parse_section_domain(spec.section)
            nested = ColdCorpusWriter(
                core,
                domain=section_domain or default_domain,
                fact_weight=active.fact_weight,
                link_weight=active.link_weight,
            )
            nested.aliases = active.aliases
            nested.image_data = active.image_data
            nested.result = active.result
            import_ahm_file(
                core,
                imported,
                default_domain=section_domain or default_domain,
                _visited=visited | {marker},
                writer=nested,
            )
            active.aliases = nested.aliases
            active.image_data = nested.image_data
            active.result = nested.result
    for module in document.modules:
        if module.kind == "module":
            active.domain = default_domain
        _apply_module(active, module)
    return active.result
