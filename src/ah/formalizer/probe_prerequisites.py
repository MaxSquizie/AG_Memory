"""Accepted choices required by a later addressed question.

The displayed premise is the accepted payload, never a fresh caller paraphrase.
Liveness is checked both before asking and when consuming the dependent proof.
"""
from copy import deepcopy
from dataclasses import dataclass, asdict
from .canonical_ledger import digest


@dataclass(frozen=True)
class AcceptedSelection:
    slot: str
    value: dict
    proof: dict

    def record(self):return asdict(self)

    def errors(self,state,visiting=None):
        from .structural_tasks import licensed_in_scope as licensed
        decision=state.decisions.get(self.proof.get('decision_ref'))
        if decision is None or decision.slot_id!=self.slot:return ('PREMISE_SLOT_MISMATCH',)
        if digest(self.value)!=self.proof.get('payload_hash'):return ('PREMISE_PAYLOAD_CHANGED',)
        if not licensed(state,self.proof,_visiting=visiting):return ('PREMISE_NOT_LICENSED',)
        return ()

    def wording(self):
        return '\nPreserve this previously selected interpretation: '+self.value['label']+'.'


def accepted(slot,selection):
    value,proof=selection
    return AcceptedSelection(slot,deepcopy(value),deepcopy(proof))


def from_proof(state,proof):
    """Recover the recorded choice when a source collector retains receipts."""
    decision=state.decisions.get(proof.get('decision_ref'))
    for row in reversed(state.syntax_trace):
        if row.get('kind')!='STRUCTURAL_TASK' or row.get('decision_ref')!=proof.get('decision_ref'):continue
        for value in row.get('alternatives',()):
            if digest(value)==proof.get('payload_hash'):
                return accepted(decision.slot_id if decision else '',(value,proof))
    return accepted('',({},proof))  # Invalid declaration; cannot supply a premise.


def errors(state,requirements,visiting=None):
    return tuple(dict.fromkeys(e for r in requirements for e in r.errors(state,visiting)))


def restored(records):
    return tuple(AcceptedSelection(**r) for r in records)
