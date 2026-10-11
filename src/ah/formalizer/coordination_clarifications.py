"""Apply a declared scope choice to the frozen T2 inventory, without rescanning."""
from .clarifications import choice
from .component_policy import policy
from .coordination_scope import alternatives, install
from .state import Decision, Ground


def apply(state, release):
    cfg=policy(release)
    if not cfg: return
    for row in state.syntax_trace:
        if row.get('kind')!='COORDINATION' or not row.get('scope_alternatives'):
            continue
        ids=tuple(c['candidate_id'] for c in row['scope_alternatives'])
        selected=choice(state,row['decision_ref'],ids)
        if selected is None: continue
        if row.get('selected_scope') not in {None,selected}:
            raise ValueError('CLARIFICATION_STRUCTURE_STALE')
        if row.get('selected_scope') is None:
            by_id={f.frame_id:f for f in state.frames}
            local=[by_id[fid] for fid in row['local_eligible']]
            for f in local:
                f.semantic['structural_unresolved']=not row['local_eligible'][f.frame_id]
            conjuncts=[by_id[fid] for fid in row['conjunct_refs']]
            region=next(r for r in state.region_forest.regions if r.region_id==row['composition_region'])
            options=alternatives(state,region,conjuncts,local,row['coordination_anchors'],cfg['max_candidates'])
            if tuple(c['candidate_id'] for c in options)!=ids:
                raise ValueError('CLARIFICATION_STRUCTURE_STALE')
            picked=next(c for c in options if c['candidate_id']==selected)
            install(picked,conjuncts,state.frames,region,row['decision_ref'])
            row['selected_scope']=selected
        d=Decision('coordination',row['decision_ref'],ids)
        d.selected,d.outcome,d.lifecycle=(selected,),'RESOLVED','PROVISIONAL'
        d.grounds.append(Ground('C','explicit clarification selection',selected))
        state.decisions[row['decision_ref']]=d
