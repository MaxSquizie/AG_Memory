from __future__ import annotations

from ah.model import Hypernode, Ref, RefKind, Template


class ValidationError(ValueError):
    pass


def validate_ref_exists(store: "AHStoreLike", ref: Ref) -> None:
    if not store.has_uid(ref.uid):
        raise ValidationError(f"Dangling ref: {ref.kind.value}:{ref.uid}")
    actual = store.kind_of(ref.uid)
    if actual is not ref.kind:
        raise ValidationError(
            f"Ref kind mismatch for {ref.uid}: expected {ref.kind.value}, actual {actual.value}"
        )


def validate_hypernode(store: "AHStoreLike", node: Hypernode) -> Template:
    validate_ref_exists(store, node.template)
    template = store.get_template(node.template.uid)

    unexpected = set(node.actants) - set(template.roles)
    if unexpected:
        names = ", ".join(sorted(role.value for role in unexpected))
        raise ValidationError(f"Actants not allowed by template {template.uid}: {names}")

    for ref in node.actants.values():
        validate_ref_exists(store, ref)

    return template


class AHStoreLike:
    def has_uid(self, uid: str) -> bool: ...
    def kind_of(self, uid: str) -> RefKind: ...
    def get_template(self, uid: str) -> Template: ...
