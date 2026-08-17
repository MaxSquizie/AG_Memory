from __future__ import annotations

import unittest

from ah.core import AHCore, SequentialUidGenerator
from ah.diagnostics import analyze_propagation
from ah.model import ActantRole, Domain, Property


class PropagationAuditV034Tests(unittest.TestCase):
    def test_feed_forward_lexical_graph_is_acyclic(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        symbol = core.ensure_abstract_symbol("есть")
        template = core.add_template(Domain.P, core.ref(symbol.uid), (ActantRole.SUBJECT,))
        entity = core.add_entity(
            Domain.P, properties={"name": Property("name", "Пользователь", "str")}
        )
        node, _ = core.add_hypernode(
            Domain.P, core.ref(template.uid), {ActantRole.SUBJECT: core.ref(entity.uid)}, weight=0.4
        )
        audit = analyze_propagation(core)
        self.assertTrue(audit.acyclic)
        self.assertEqual(audit.cyclic_components, ())
        self.assertEqual(audit.max_path_hops, 3)  # S -> T -> N -> M
        self.assertTrue(any(e.source_uid == symbol.uid and e.target_uid == template.uid for e in audit.edges))
        self.assertTrue(any(e.source_uid == template.uid and e.target_uid == node.uid for e in audit.edges))

    def test_directed_link_cycle_is_reported(self) -> None:
        core = AHCore(uid_generator=SequentialUidGenerator())
        a = core.add_entity(Domain.C, properties={"name": Property("name", "A", "str")})
        b = core.add_entity(Domain.C, properties={"name": Property("name", "B", "str")})
        core.add_link("TEST", core.ref(a.uid), core.ref(b.uid), 0.4)
        core.add_link("TEST", core.ref(b.uid), core.ref(a.uid), 0.4)
        audit = analyze_propagation(core)
        self.assertFalse(audit.acyclic)
        self.assertEqual(len(audit.cyclic_components), 1)
        self.assertEqual(set(audit.cyclic_components[0]), {a.uid, b.uid})
        self.assertIsNone(audit.max_path_hops)


if __name__ == "__main__":
    unittest.main()
