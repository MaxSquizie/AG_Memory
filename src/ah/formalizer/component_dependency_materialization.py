"""Typed syntax descriptions, licensed by released senses, never identity links."""
from .canonical_ledger import digest
from .component_dependency_domains import clean


def prepare_entities(deps,evidence,morphology,lexical):
    for d in deps:
        t=d['head_ref'];e=evidence[t]
        morphology[t]=d['morph']
        lexical[t]={'head_ref':t,'anchor_refs':[t],'surface':e.span,'mention_ref':t}


def describe_dependencies(deps,describe,evidence,owners,pending,cfg):
    for d in deps:
        head,host=d['head_ref'],d['host_ref'];e=evidence[head]
        variant=next(v for v in e.variants if clean(v)==d['morph'])
        child=describe(e,variant,{host:cfg['nominal_host_role'],head:cfg['preposition_nominal_role']})
        child.semantic['nominal_dependency_kind']=d['kind']
        child.semantic['dependency_evidence']=d
        owners[head]=child;pending.append((host,child))


def prepare_candidate(frame,state,release):
    """D-grounded structural sense; ordinary T5 mapping still verifies real AH T."""
    from .t3_sources import build_source_traces
    cfg=release.entries('ProposalPolicy')[0]['composition']
    kind=frame.semantic['nominal_dependency_kind'];sid=cfg['dependency_senses'][kind]
    d=frame.semantic['dependency_evidence'];evidence={e.token_id:e for e in state.evidence}
    head,host=d['head_ref'],d['host_ref'];reading=d['morph']
    valid=any(clean(v)==reading for v in evidence[head].variants)
    valid &= frame.semantic['proposed_roles']=={host:cfg['nominal_host_role'],head:cfg['preposition_nominal_role']}
    if kind=='GENITIVE': valid &= 'gen' in reading['cases']
    elif kind=='CASE_DEPENDENCY':
        valid &= d.get('case') in cfg.get('nominal_dependency_cases',()) and d.get('case') in reading['cases']
        valid &= head!=host
    else:
        marker=evidence.get(d.get('marker_ref'))
        valid &= bool(marker and marker.span in cfg['apposition_markers'] and
                      evidence[host].end<=marker.start and marker.end<=evidence[head].start and 'nom' in reading['cases'])
    if not valid:
        frame.semantic['structural_unresolved']=True
        state.diag('COMPONENT_DEPENDENCY_LICENSE_FAILED',frame.frame_id)
    roles=frame.semantic['proposed_roles'];cid='syntax:'+digest([frame.frame_id,sid,roles])
    spec={'candidate_id':cid,'sense_id':sid,'label':kind+' nominal dependency (not identity/ownership)',
          'sense_kind':'KNOWN','roles':roles,'implicit_roles':[],'state_class':'STATE',
          'valency_ref':'released-dependency:'+kind}
    traces=build_source_traces(frame.frame_id,'predicate_value',schema_candidates=[cid],rs_senses=[cid],
        rx3_prior=[],wc_reads=[],rx3_applicable=False,wc_applicable=False,open_candidate=None,
        open_path_verified=True,resource_versions=(release.sha256,))
    frame.semantic.update(has_known_senses=True,source_blocked=False,candidate_specs={cid:spec},
                          source_traces=traces,region=None,temporal_unresolved=False)
    return [spec]
