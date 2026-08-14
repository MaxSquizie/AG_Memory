from __future__ import annotations

from dataclasses import replace
import shlex
from typing import Any, Iterable

from ah.core import AHCore
from ah.model import (
    ActantRole,
    Domain,
    FunctionSymbol,
    Group,
    Hypernode,
    Link,
    Property,
    Ref,
    RefKind,
    SemanticEntity,
    Template,
)

from .contracts import DSLError, DSLResult


class DSLInterpreter:
    """Small textual DSL mapped only to canonical AH Core operations.

    Syntax is intentionally boring and deterministic:

        findRoles role=LOCATION value=@M_1 domain=H
        findRoles role=LOCATION value=@M_1 | findLists | where meta.TYPE=Episode
        addLink relation=IS-A source=@M_1 target=@M_2 weight=0.2

    Pipeline stages consume the previous result where the canonical operation has a
    natural collection operand. The DSL never bypasses AHCore.
    """

    def __init__(self, core: AHCore) -> None:
        self.core = core

    def execute(self, text: str) -> DSLResult:
        stages = self._split_pipeline(text)
        if not stages:
            raise DSLError("Empty DSL command")
        value: Any = None
        command_names: list[str] = []
        for index, tokens in enumerate(stages):
            if not tokens:
                continue
            name = tokens[0]
            command_names.append(name)
            args, positional = self._parse_args(tokens[1:])
            value = self._execute_stage(name, args, positional, value if index else None)
        return DSLResult(" | ".join(command_names), value, self._count(value))

    @staticmethod
    def _split_pipeline(text: str) -> list[list[str]]:
        lex = shlex.shlex(text, posix=True, punctuation_chars="|")
        lex.whitespace_split = True
        lex.commenters = "#"
        stages: list[list[str]] = [[]]
        for token in lex:
            if token == "|":
                stages.append([])
            else:
                stages[-1].append(token)
        return [stage for stage in stages if stage]

    @staticmethod
    def _parse_args(tokens: list[str]) -> tuple[dict[str, str], list[str]]:
        args: dict[str, str] = {}
        positional: list[str] = []
        for token in tokens:
            if "=" in token:
                key, raw = token.split("=", 1)
                args[key] = raw
            else:
                positional.append(token)
        return args, positional

    @staticmethod
    def _count(value: Any) -> int | None:
        if isinstance(value, (tuple, list, set, frozenset, dict)):
            return len(value)
        return None

    def _domains(self, args: dict[str, str]) -> tuple[Domain, ...] | None:
        raw = args.get("domain") or args.get("domains")
        if not raw or raw.upper() in {"ALL", "*"}:
            return None
        try:
            return tuple(Domain(item.strip().upper()) for item in raw.split(",") if item.strip())
        except ValueError as exc:
            raise DSLError(f"Invalid domain list: {raw}") from exc

    def _ref(self, raw: str) -> Ref:
        uid = raw[1:] if raw.startswith("@") else raw
        if not self.core.store.has_uid(uid):
            raise DSLError(f"Unknown UID: {uid}")
        return self.core.ref(uid)

    def _refs(self, raw: str) -> tuple[Ref, ...]:
        if not raw.strip():
            return ()
        return tuple(self._ref(item.strip()) for item in raw.split(",") if item.strip())

    @staticmethod
    def _scalar(raw: str) -> Any:
        low = raw.casefold()
        if low == "true":
            return True
        if low == "false":
            return False
        if low in {"none", "null"}:
            return None
        try:
            return int(raw)
        except ValueError:
            pass
        try:
            return float(raw)
        except ValueError:
            return raw

    @staticmethod
    def _as_refs(value: Any) -> tuple[Ref, ...]:
        if value is None:
            return ()
        if isinstance(value, Ref):
            return (value,)
        if isinstance(value, (SemanticEntity, FunctionSymbol, Group, Template, Hypernode, Link)):
            kind = {
                SemanticEntity: RefKind.M,
                FunctionSymbol: RefKind.G,
                Group: RefKind.K,
                Template: RefKind.T,
                Hypernode: RefKind.N,
                Link: RefKind.L,
            }[type(value)]
            return (Ref(value.uid, kind),)
        if isinstance(value, Iterable) and not isinstance(value, (str, bytes, dict)):
            out: list[Ref] = []
            for item in value:
                out.extend(DSLInterpreter._as_refs(item))
            by_uid = {r.uid: r for r in out}
            return tuple(by_uid[uid] for uid in sorted(by_uid))
        return ()

    def _execute_stage(
        self,
        name: str,
        args: dict[str, str],
        positional: list[str],
        previous: Any,
    ) -> Any:
        key = name.casefold()
        domains = self._domains(args)

        # ---------- mutation operations ----------
        if key == "addabstractsymbol":
            raw = args.get("forms") or (positional[0] if positional else "")
            forms = {x.strip() for x in raw.split(",") if x.strip()}
            return self.core.add_abstract_symbol(forms)

        if key == "editabstractsymbol":
            uid = (args.get("uid") or (positional[0] if positional else "")).lstrip("@")
            forms = {x.strip() for x in args.get("forms", "").split(",") if x.strip()}
            return self.core.edit_abstract_symbol(uid, forms)

        if key == "addelement":
            return self._add_element(args)

        if key == "editelement":
            return self._edit_element(args)

        if key in {"addproperty", "editproperty"}:
            uid = (args.get("uid") or "").lstrip("@")
            if not uid:
                raise DSLError(f"{name} requires uid")
            prop_name = args.get("name")
            if not prop_name:
                raise DSLError(f"{name} requires name")
            scope = args.get("scope", args.get("set", "Pr")).upper()
            value = self._scalar(args.get("value", ""))
            if scope == "MT":
                return (
                    self.core.add_meta_property(uid, prop_name, value)
                    if key == "addproperty"
                    else self.core.edit_meta_property(uid, prop_name, value)
                )
            if scope != "PR":
                raise DSLError("property scope must be Pr or Mt")
            prop = Property(
                prop_name,
                value,
                args.get("type", "str"),
                args.get("unit") or None,
            )
            return self.core.add_property(uid, prop) if key == "addproperty" else self.core.edit_property(uid, prop)

        if key == "addlink":
            relation = args.get("relation") or args.get("id")
            if not relation:
                raise DSLError("addLink requires relation")
            return self.core.add_link(
                relation,
                self._ref(args["source"]),
                self._ref(args["target"]),
                float(args.get("weight", "0.2")),
            )

        # ---------- query operations ----------
        if key == "getabstractsymbol":
            return self.core.get_abstract_symbol((args.get("uid") or positional[0]).lstrip("@"))

        if key == "findabstractsymbols":
            raw = args.get("forms") or ",".join(positional)
            return self.core.find_abstract_symbols({x.strip() for x in raw.split(",") if x.strip()})

        if key in {"getsreference", "findsreferences", "getmreference", "findmreferences"}:
            uid = (args.get("uid") or positional[0]).lstrip("@")
            fn = {
                "getsreference": self.core.get_s_reference,
                "findsreferences": self.core.find_s_references,
                "getmreference": self.core.get_m_reference,
                "findmreferences": self.core.find_m_references,
            }[key]
            return fn(uid, domains)

        if key == "getsymbol":
            uid = (args.get("uid") or positional[0]).lstrip("@")
            return self.core.get_symbol(uid, domains)

        if key == "findsymbols":
            props = {
                k.removeprefix("pr."): self._scalar(v)
                for k, v in args.items()
                if k.startswith("pr.")
            }
            if "name" in args:
                props["name"] = self._scalar(args["name"])
            return self.core.find_symbols(props, domains)

        if key == "getlist":
            uid = (args.get("uid") or positional[0]).lstrip("@")
            return self.core.get_list(uid, domains)

        if key == "findlists":
            explicit = args.get("member")
            refs = (self._ref(explicit),) if explicit else self._as_refs(previous)
            if not refs:
                raise DSLError("findLists requires member=... or pipeline input")
            out: dict[str, Group] = {}
            for ref in refs:
                for group in self.core.find_lists(ref, domains):
                    out[group.uid] = group
            return tuple(out[uid] for uid in sorted(out))

        if key == "gettemplate":
            uid = (args.get("uid") or positional[0]).lstrip("@")
            return self.core.get_template(uid, domains)

        if key == "gethypernode":
            uid = (args.get("uid") or positional[0]).lstrip("@")
            return self.core.get_hypernode(uid, domains)

        if key == "findhypernodes":
            explicit = args.get("operand")
            refs = (self._ref(explicit),) if explicit else self._as_refs(previous)
            if not refs:
                raise DSLError("findHypernodes requires operand=... or pipeline input")
            out: dict[str, Hypernode] = {}
            for ref in refs:
                for node in self.core.find_hypernodes(ref, domains):
                    out[node.uid] = node
            return tuple(out[uid] for uid in sorted(out))

        if key == "findroles":
            raw_role = args.get("role")
            if not raw_role:
                raise DSLError("findRoles requires role")
            try:
                role = ActantRole(raw_role.upper().replace("_", "-"))
            except ValueError as exc:
                raise DSLError(f"Unknown role: {raw_role}") from exc
            explicit = args.get("value")
            refs = (self._ref(explicit),) if explicit else self._as_refs(previous)
            if not refs:
                raise DSLError("findRoles requires value=... or pipeline input")
            out: dict[str, Hypernode] = {}
            for ref in refs:
                for node in self.core.find_roles(role, ref, domains):
                    out[node.uid] = node
            return tuple(out[uid] for uid in sorted(out))

        if key == "getlink":
            uid = (args.get("uid") or positional[0]).lstrip("@")
            return self.core.get_link(uid)

        if key == "findlinks":
            explicit = args.get("element")
            refs = (self._ref(explicit),) if explicit else self._as_refs(previous)
            if not refs:
                raise DSLError("findLinks requires element=... or pipeline input")
            out: dict[str, Link] = {}
            for ref in refs:
                for link in self.core.find_links(ref):
                    out[link.uid] = link
            return tuple(out[uid] for uid in sorted(out))

        # ---------- compositional helpers; read-only extensions ----------
        if key == "where":
            return self._where(previous, args)

        if key == "refs":
            return self._as_refs(previous)

        if key == "unique":
            refs = self._as_refs(previous)
            return refs

        raise DSLError(f"Unknown DSL operation: {name}")

    def _add_element(self, args: dict[str, str]) -> Any:
        try:
            domain = Domain(args.get("domain", "C").upper())
        except ValueError as exc:
            raise DSLError("addElement requires valid domain=C|P|H") from exc
        kind = args.get("kind", "M").upper()
        if kind == "M":
            props: dict[str, Property] = {}
            if "name" in args:
                props["name"] = Property("name", args["name"], "str")
            for key, raw in args.items():
                if key.startswith("pr."):
                    prop_name = key[3:]
                    props[prop_name] = Property(prop_name, self._scalar(raw), "auto")
            return self.core.add_entity(domain, props)
        if kind == "G":
            return self.core.add_function(domain, args["function"], self._refs(args.get("operands", "")))
        if kind == "K":
            return self.core.add_group(domain, self._refs(args.get("members", "")))
        if kind == "T":
            roles = tuple(ActantRole(x.strip().upper().replace("_", "-")) for x in args.get("roles", "").split(",") if x.strip())
            return self.core.add_template(domain, self._ref(args["predicate"]), roles)
        if kind == "N":
            template = self._ref(args["template"])
            actants: dict[ActantRole, Ref] = {}
            reserved = {"domain", "kind", "template", "weight"}
            for key, raw in args.items():
                if key in reserved:
                    continue
                try:
                    role = ActantRole(key.upper().replace("_", "-"))
                except ValueError:
                    continue
                actants[role] = self._ref(raw)
            return self.core.add_hypernode(domain, template, actants, float(args.get("weight", "0.4")))[0]
        raise DSLError(f"Unsupported addElement kind: {kind}")

    def _edit_element(self, args: dict[str, str]) -> Any:
        raw_uid = args.get("uid")
        if not raw_uid:
            raise DSLError("editElement requires uid")
        uid = raw_uid.lstrip("@")
        if not self.core.store.has_uid(uid):
            raise DSLError(f"Unknown UID: {uid}")
        kind = self.core.store.kind_of(uid)
        if kind is RefKind.L:
            link = self.core.store.get_link(uid)
            if "weight" not in args:
                raise DSLError("editElement on L currently supports weight")
            updated = replace(link, weight=float(args["weight"]))
            return self.core.edit_link(updated)
        domain = self.core.store.domain_of(uid)
        assert domain is not None
        element = self.core.store.get_element(domain, uid)
        if isinstance(element, Hypernode) and "weight" in args:
            return self.core.edit_element(domain, replace(element, weight=float(args["weight"])))
        if isinstance(element, FunctionSymbol) and "function" in args:
            return self.core.edit_element(domain, replace(element, function_id=args["function"]))
        if isinstance(element, Group) and "members" in args:
            return self.core.edit_element(domain, replace(element, members=self._refs(args["members"])))
        raise DSLError("editElement currently requires a supported field for the target type")

    def _where(self, previous: Any, args: dict[str, str]) -> tuple[Any, ...]:
        if previous is None or isinstance(previous, (str, bytes, dict)):
            raise DSLError("where requires pipeline collection input")
        values = tuple(previous) if isinstance(previous, Iterable) else (previous,)
        out: list[Any] = []
        for item in values:
            if self._matches_where(item, args):
                out.append(item)
        return tuple(out)

    def _matches_where(self, item: Any, args: dict[str, str]) -> bool:
        uid = getattr(item, "uid", None)
        for key, raw in args.items():
            expected = self._scalar(raw)
            if key == "kind":
                if uid is None or self.core.store.kind_of(uid).value != str(expected).upper():
                    return False
            elif key == "domain":
                if uid is None or self.core.store.domain_of(uid) != Domain(str(expected).upper()):
                    return False
            elif key.startswith("meta."):
                meta = getattr(item, "meta", {})
                if meta.get(key[5:]) != expected:
                    return False
            elif key.startswith("pr."):
                props = getattr(item, "properties", {})
                prop = props.get(key[3:])
                if prop is None or prop.value != expected:
                    return False
            elif key == "relation":
                if not isinstance(item, Link) or item.relation_id.upper() != str(expected).upper():
                    return False
            else:
                if getattr(item, key, object()) != expected:
                    return False
        return True
