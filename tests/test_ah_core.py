from __future__ import annotations

import unittest

from ah.core import AHCore, SequentialUidGenerator
from ah.core.validation import ValidationError
from ah.model import ActantRole, Domain, Property, RefKind


class AHCoreTests(unittest.TestCase):
    def setUp(self) -> None:
        self.core = AHCore(uid_generator=SequentialUidGenerator())

    def _read_template_fixture(self):
        s_read = self.core.add_abstract_symbol({"читать", "читает"})
        t_read = self.core.add_template(
            Domain.C,
            self.core.ref(s_read.uid),
            (ActantRole.SUBJECT, ActantRole.OBJECT),
        )
        ivan = self.core.add_entity(
            Domain.P,
            properties={"name": Property("name", "Иван", "str")},
        )
        book = self.core.add_entity(
            Domain.C,
            properties={"name": Property("name", "книга", "str")},
        )
        return t_read, ivan, book

    def test_domain_local_hypernode_dedup(self) -> None:
        t_read, ivan, book = self._read_template_fixture()
        actants = {
            ActantRole.SUBJECT: self.core.ref(ivan.uid),
            ActantRole.OBJECT: self.core.ref(book.uid),
        }

        first, created = self.core.add_hypernode(
            Domain.P, self.core.ref(t_read.uid), actants, weight=0.5
        )
        second, created_second = self.core.add_hypernode(
            Domain.P, self.core.ref(t_read.uid), actants, weight=0.9
        )

        self.assertTrue(created)
        self.assertFalse(created_second)
        self.assertEqual(first.uid, second.uid)
        self.assertEqual(second.meta["occurrence_count"], 2)
        self.assertEqual(second.weight, 0.5, "duplicate must not directly rewrite w")

        same_semantics_h, created_h = self.core.add_hypernode(
            Domain.H, self.core.ref(t_read.uid), actants, weight=0.5
        )
        self.assertTrue(created_h)
        self.assertNotEqual(first.uid, same_semantics_h.uid)

    def test_template_rejects_unknown_role(self) -> None:
        t_read, ivan, _ = self._read_template_fixture()
        with self.assertRaises(ValidationError):
            self.core.add_hypernode(
                Domain.P,
                self.core.ref(t_read.uid),
                {ActantRole.LOCATION: self.core.ref(ivan.uid)},
                weight=0.5,
            )

    def test_nested_hypernode_can_be_actant(self) -> None:
        s_move = self.core.add_abstract_symbol({"переехать"})
        s_say = self.core.add_abstract_symbol({"сказать"})
        t_move = self.core.add_template(
            Domain.C, self.core.ref(s_move.uid), (ActantRole.SUBJECT, ActantRole.LOCATION)
        )
        t_say = self.core.add_template(
            Domain.C, self.core.ref(s_say.uid), (ActantRole.SUBJECT, ActantRole.OBJECT)
        )
        ivan = self.core.add_entity(Domain.P)
        masha = self.core.add_entity(Domain.P)
        paris = self.core.add_entity(Domain.C)

        move, _ = self.core.add_hypernode(
            Domain.P,
            self.core.ref(t_move.uid),
            {
                ActantRole.SUBJECT: self.core.ref(masha.uid),
                ActantRole.LOCATION: self.core.ref(paris.uid),
            },
            0.5,
        )
        say, created = self.core.add_hypernode(
            Domain.H,
            self.core.ref(t_say.uid),
            {
                ActantRole.SUBJECT: self.core.ref(ivan.uid),
                ActantRole.OBJECT: self.core.ref(move.uid),
            },
            0.5,
        )
        self.assertTrue(created)
        self.assertEqual(say.actants[ActantRole.OBJECT].kind, RefKind.N)

    def test_transaction_is_atomic_on_exception(self) -> None:
        before = self.core.store.has_uid("M_1")
        self.assertFalse(before)

        with self.assertRaises(RuntimeError):
            with self.core.transaction() as tx:
                tx.add_entity(Domain.C)
                raise RuntimeError("abort")

        self.assertFalse(self.core.store.has_uid("M_1"))

    def test_transaction_commits(self) -> None:
        with self.core.transaction() as tx:
            entity = tx.add_entity(Domain.C)
            uid = entity.uid
        self.assertTrue(self.core.store.has_uid(uid))

    def test_duplicate_symbol_insert_is_atomic(self) -> None:
        first = self.core.add_abstract_symbol({"Крипл"})
        before = set(self.core.store.all_uids())
        with self.assertRaises(ValueError):
            self.core.add_abstract_symbol({"Крипл"})
        self.assertEqual(set(self.core.store.all_uids()), before)
        self.assertEqual(self.core.store.find_symbol_by_form("Крипл").uid, first.uid)

    def test_uid_is_global_across_domains(self) -> None:
        entity = self.core.add_entity(Domain.C, uid="M_SHARED")
        self.assertEqual(entity.uid, "M_SHARED")
        with self.assertRaises(ValueError):
            self.core.add_entity(Domain.P, uid="M_SHARED")


if __name__ == "__main__":
    unittest.main()
