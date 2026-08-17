from __future__ import annotations

from dataclasses import dataclass

from ah.config import ContextSettings
from ah.core import AHCore
from ah.model import (
    AbstractSymbol,
    ActantRole,
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

from .contracts import ProjectionBlock, ProjectionMode
from .function_registry import FunctionRegistry


@dataclass(frozen=True, slots=True)
class _RenderState:
    stack: tuple[str, ...] = ()
    depth: int = 0

    def descend(self, uid: str) -> "_RenderState":
        return _RenderState(self.stack + (uid,), self.depth + 1)


class SemanticProjector:
    """Read-only AH -> stable semantic representation.

    ACTIVE controls only how the root is represented. Every reference underneath
    it is rendered in DEPENDENCY mode, so dereferencing can never recursively
    turn the graph into a full dump or modify Workspace membership.
    """

    def __init__(
        self,
        core: AHCore,
        settings: ContextSettings,
        functions: FunctionRegistry | None = None,
    ) -> None:
        self.core = core
        self.settings = settings
        self.functions = functions or FunctionRegistry()

    def active_block(self, ref: Ref) -> ProjectionBlock:
        semantic = self._render(ref, ProjectionMode.ACTIVE, _RenderState())
        props: tuple[Property, ...] = ()
        obj = self._resolve(ref)
        if isinstance(obj, (SemanticEntity, Hypernode, Group)):
            props = tuple(obj.properties.values())
        return ProjectionBlock(ref, ProjectionMode.ACTIVE, semantic, props)

    def dependency_text(self, ref: Ref) -> str:
        return self._render(ref, ProjectionMode.DEPENDENCY, _RenderState())

    def inference_text_for_ref(self, ref: Ref) -> str:
        return self._render(ref, ProjectionMode.DEPENDENCY, _RenderState())

    def _resolve(self, ref: Ref):
        if ref.kind is RefKind.S:
            return self.core.store.get_symbol(ref.uid)
        if ref.kind is RefKind.L:
            return self.core.store.get_link(ref.uid)
        return self.core.store.get_element_any_domain(ref.uid)

    def _label(self, ref: Ref, semantic: str) -> str:
        if not self.settings.include_structural_uids:
            return semantic
        return f"[{ref.uid}] {semantic}"

    @staticmethod
    def _symbol_form(symbol: AbstractSymbol) -> str:
        # R is recognition data, not a separately exposed field. We only choose a
        # deterministic representative spelling for serialization.
        return sorted(symbol.forms, key=lambda s: (len(s), s.casefold(), s))[0]

    @staticmethod
    def _property_text(prop: Property) -> str:
        unit = f" {prop.unit}" if prop.unit else ""
        return f"{prop.name}={prop.value!r}{unit}"

    def _render(self, ref: Ref, mode: ProjectionMode, state: _RenderState) -> str:
        if state.depth > self.settings.max_dependency_depth:
            return self._label(ref, "<dependency-depth-limit>")
        if ref.uid in state.stack:
            return self._label(ref, "<cyclic-reference>")

        obj = self._resolve(ref)
        child_state = state.descend(ref.uid)

        if isinstance(obj, AbstractSymbol):
            semantic = self._symbol_form(obj)
            return self._label(ref, semantic)

        if isinstance(obj, SemanticEntity):
            name = obj.properties.get("name")
            semantic = str(name.value) if name is not None else obj.uid
            if mode is ProjectionMode.ACTIVE:
                others = [
                    self._property_text(p)
                    for key, p in obj.properties.items()
                    if key != "name"
                ]
                if others:
                    semantic += " {" + ", ".join(others) + "}"
            return self._label(ref, semantic)

        if isinstance(obj, Template):
            predicate = self._render(obj.predicate, ProjectionMode.DEPENDENCY, child_state)
            if mode is ProjectionMode.ACTIVE:
                semantic = f"predicate={predicate}; roles=[{', '.join(r.value for r in obj.roles)}]"
            else:
                semantic = predicate
            return self._label(ref, semantic)

        if isinstance(obj, Hypernode):
            # H dialogue events own their raw utterance text.  For ACTIVE operator/
            # AgentContext projection the utterance itself is the most useful
            # human-readable semantics; the generic VYSKAZAT template is only a
            # structural carrier and must not hide every turn behind the same label.
            if mode is ProjectionMode.ACTIVE and bool(obj.meta.get("event_instance", False)):
                text_prop = obj.properties.get("text")
                if text_prop is not None and isinstance(text_prop.value, str):
                    speaker = "реплика"
                    subject_ref = obj.actants.get(ActantRole.SUBJECT)
                    if subject_ref is not None and subject_ref.kind is RefKind.M:
                        try:
                            subject = self.core.store.get_element_any_domain(subject_ref.uid)
                            if isinstance(subject, SemanticEntity):
                                identity_role = str(subject.meta.get("identity_role", "")).upper()
                                if identity_role == "USER":
                                    speaker = "реплика пользователя"
                                elif identity_role == "SELF":
                                    speaker = "реплика агента"
                        except Exception:
                            pass
                    semantic = f"{speaker}: {text_prop.value}"
                    return self._label(ref, semantic)

            template = self.core.store.get_template(obj.template.uid)
            predicate = self._render(template.predicate, ProjectionMode.DEPENDENCY, child_state)
            role_chunks: list[str] = []
            for role in template.roles:
                actant = obj.actants.get(role)
                if actant is None:
                    continue
                role_chunks.append(
                    f"{role.value}={self._render(actant, ProjectionMode.DEPENDENCY, child_state)}"
                )
            semantic = f"{predicate}({', '.join(role_chunks)})"
            if mode is ProjectionMode.ACTIVE and obj.properties:
                semantic += " {" + ", ".join(self._property_text(p) for p in obj.properties.values()) + "}"
            return self._label(ref, semantic)

        if isinstance(obj, Link):
            source = self._render(obj.source, ProjectionMode.DEPENDENCY, child_state)
            target = self._render(obj.target, ProjectionMode.DEPENDENCY, child_state)
            semantic = f"{source} --{obj.relation_id}--> {target}"
            return self._label(ref, semantic)

        if isinstance(obj, FunctionSymbol):
            operands = tuple(
                self._render(r, ProjectionMode.DEPENDENCY, child_state)
                for r in obj.operands
            )
            semantic = self.functions.render(obj.function_id, operands)
            return self._label(ref, semantic)

        if isinstance(obj, Group):
            members = tuple(
                self._render(r, ProjectionMode.DEPENDENCY, child_state)
                for r in obj.members
            )
            name = obj.properties.get("name")
            identity = str(name.value) if name is not None else obj.uid
            if mode is ProjectionMode.ACTIVE:
                semantic = f"{identity} = group[{'; '.join(members)}]"
                extra = [
                    self._property_text(p)
                    for key, p in obj.properties.items()
                    if key != "name"
                ]
                if extra:
                    semantic += " {" + ", ".join(extra) + "}"
            else:
                semantic = f"{identity}[{'; '.join(members)}]"
            return self._label(ref, semantic)

        raise TypeError(f"Unsupported projection type for {ref}: {type(obj).__name__}")
