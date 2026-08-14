from __future__ import annotations

import unittest

from ah.core import AHCore, SequentialUidGenerator
from ah.dsl import DSLInterpreter
from ah.model import ActantRole, Domain, Property


class DSLTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())
        self.dsl = DSLInterpreter(self.core)

    def test_normative_query_operations_and_composition(self) -> None:
        s = self.core.add_abstract_symbol({"быть"})
        t = self.core.add_template(Domain.H, self.core.ref(s.uid), (ActantRole.SUBJECT, ActantRole.LOCATION))
        actor = self.core.add_entity(Domain.H, {"name": Property("name", "Иван", "str")})
        place = self.core.add_entity(Domain.H, {"name": Property("name", "Москва", "str")})
        n, _ = self.core.add_hypernode(
            Domain.H,
            self.core.ref(t.uid),
            {ActantRole.SUBJECT: self.core.ref(actor.uid), ActantRole.LOCATION: self.core.ref(place.uid)},
            0.4,
        )
        episode = self.core.add_group(
            Domain.H,
            (self.core.ref(n.uid),),
            meta={"TYPE": "Episode"},
        )

        result = self.dsl.execute(
            f"findRoles role=LOCATION value=@{place.uid} domain=H | findLists domain=H | where meta.TYPE=Episode"
        )
        self.assertEqual(result.count, 1)
        self.assertEqual(result.value[0].uid, episode.uid)

    def test_mutation_dsl_maps_to_core(self) -> None:
        added = self.dsl.execute('addAbstractSymbol forms="читать,читает"').value
        entity = self.dsl.execute('addElement domain=C kind=M name="Иван"').value
        self.dsl.execute(f'addProperty uid=@{entity.uid} name=age value=32 type=int')
        found = self.dsl.execute('findSymbols domain=C name="Иван"').value
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0].properties["age"].value, 32)
        self.assertIn("читать", added.forms)

    def test_find_links_is_incident_to_element(self) -> None:
        a = self.core.add_entity(Domain.C, {"name": Property("name", "A", "str")})
        b = self.core.add_entity(Domain.C, {"name": Property("name", "B", "str")})
        link = self.core.add_link("IS-A", self.core.ref(a.uid), self.core.ref(b.uid), 0.2)
        result = self.dsl.execute(f"findLinks element=@{b.uid}")
        self.assertEqual(tuple(x.uid for x in result.value), (link.uid,))


if __name__ == "__main__":
    unittest.main()
