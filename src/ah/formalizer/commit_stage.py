"""T5 journals the actual typed plan; T6 admits and applies that same plan."""
from dataclasses import asdict,dataclass
from .canonical_ledger import digest
from .store_interface import CommitDecision,MaterializationMarker,JournalRecord,TerminalOutcome

@dataclass(frozen=True)
class CommitReport:
    admitted_at_head: bool
    applied: bool
    batch_hash: str
    n_ops: int
    terminal: TerminalOutcome
    committed_fragments: tuple[str,...]=()


def commit(state,store,*,run_id,plan_ops=(),committed_fragments=(),pending=(),superseded=False):
    if not plan_ops or not committed_fragments:
        store.append_journal('resolution_log',JournalRecord('resolution_log',run_id,{'kind':'RESOLUTION','observation_id':state.source_uid,'version':state.interpretation_version,'outcomes':{k:d.outcome for k,d in state.decisions.items()},'diagnostics':[asdict(d) for d in state.diagnostics]}))
        return CommitReport(False,False,'',0,TerminalOutcome.RESOLUTION_ONLY)
    marker=MaterializationMarker(state.source_uid,state.interpretation_version)
    raw={'observation':state.observation,'resource_snapshot':state.resource_snapshot,'structural_hash':state.structural_hash,'ops':[asdict(o) for o in plan_ops],'fragments':list(committed_fragments),'run_id':run_id}
    bh=digest(raw)
    previous=next((r for r in store.scan_unprocessed(0) if r.payload.get('kind')=='BATCH' and r.payload.get('batch_hash')==bh),None)
    prechecks=tuple(previous.payload['decision'].get('precheck_refs',())) if previous else store.gate_precheck(bh,plan_ops,run_id=run_id) if hasattr(store,'gate_precheck') else ()
    D=CommitDecision(run_id,bh,marker,digest(raw['ops']),TerminalOutcome.STALE_SUPERSEDED if superseded else TerminalOutcome.APPLIED,committed=tuple(committed_fragments),precheck_refs=prechecks)
    if previous:
        recorded=dict(previous.payload['decision']); recorded['marker']=MaterializationMarker(**recorded['marker']); recorded['outcome']=TerminalOutcome(recorded['outcome'])
        D=CommitDecision(**recorded)
    else:
        decision=asdict(D); decision['outcome']=D.outcome.value
        store.append_journal('observation',JournalRecord('observation',run_id,{'kind':'BATCH','batch_hash':bh,'ops':raw['ops'],'decision':decision,'observation':state.observation,'resource_snapshot':state.resource_snapshot}))
    result=store.commit_transaction(plan_ops,marker,D)
    actual=store.ledger.data['decisions'].get(bh,{}) if hasattr(store,'ledger') else {}
    return CommitReport(result.outcome!=TerminalOutcome.PENDING_ADMISSION_ORDER,result.outcome==TerminalOutcome.APPLIED and not result.idempotent_noop,bh,len(plan_ops),result.outcome,tuple(actual.get('committed',())))
