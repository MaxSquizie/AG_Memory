"""Shared contracts for relation shells whose child inputs need no child output.

Other relations require staged owner/binder/controller preparation. Absence here
means missing producer capability, never an inadmissible language hypothesis.
"""
from dataclasses import dataclass,replace
from .composition_tree import InputSlot


@dataclass(frozen=True)
class RelationContract:
    partition: str
    minimum: int
    maximum: int | None

    def accepts(self,count):
        return count>=self.minimum and (self.maximum is None or count<=self.maximum)


CONTRACTS={
    **{kind:RelationContract('binary',2,None) for kind in ('AND','OR','XOR')},
    **{kind:RelationContract('binary',2,2) for kind in ('IMPLIES','COUNTERFACTUAL','BEFORE','AFTER','DURING')},
    'IF_ELSE':RelationContract('binary',3,3),
    **{kind:RelationContract('unary',1,1) for kind in ('NOT','QUERY')},
    'GROUP':RelationContract('group',1,1),
}


def child_request(kind,parent):
    if kind not in CONTRACTS:raise ValueError('STRUCTURAL_CHILD_PREPARATION_NOT_CONNECTED')
    slot=parent or InputSlot()
    if kind=='GROUP':return replace(slot,inside_attitude=True)
    return replace(slot,surrounding_relations=(*slot.surrounding_relations,kind))


def producer(kind):
    from . import relation_partitions
    return getattr(relation_partitions,CONTRACTS[kind].partition)
