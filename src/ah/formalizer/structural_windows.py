"""Addressed expansion permits based on current branch evidence, not depth alone."""
from .canonical_ledger import digest
from .structural_shells import live,evidence_state
from .partition_exclusions import live as exclusion_live
from .structural_forest import live as forest_live
from .validation_graph import scope


def ancestors(driver,job):
    seen=set()
    while job is not None:
        if job['job_ref'] in seen:raise ValueError('STRUCTURAL_FRONTIER_CYCLE')
        seen.add(job['job_ref']);yield job
        ref=job.get('parent_job_ref')
        if ref and ref not in driver.jobs:raise ValueError('STRUCTURAL_PARENT_JOB_MISSING')
        if not ref and job.get('parent_shell') is not None:raise ValueError('STRUCTURAL_PARENT_JOB_MISSING')
        job=driver.jobs.get(ref) if ref else None


def inspect(driver,job):
    """Inspect all recorded ancestor constraints; this does not complete a domain."""
    checked=[];reason=None
    try:chain=list(ancestors(driver,job))
    except ValueError:chain=[];reason='PARENT_CHAIN_INCOMPLETE'
    with scope():
        for parent in chain:
            driver.sync(parent)
            if parent['status']=='STALE':reason='BASIS_RETIRED';break
            forest=parent.get('forest')
            if forest is not None:
                if not forest_live(parent['state'],forest):reason='DOMAIN_BASIS_RETIRED';break
                if parent is not job:checked.append(['forest',forest['receipt_digest']])
            shell=parent.get('parent_shell')
            if shell is None:continue
            if not live(parent['state'],shell):reason='PARENT_BASIS_RETIRED';break
            checked.append(['shell',shell['receipt_digest']])
            local=evidence_state(parent['state'],shell,read_only=True)
            for row in local.syntax_trace:
                if row.get('kind')!='STRUCTURAL_PARTITION_EXCLUSION':continue
                if row.get('candidate',{}).get('combination_ref')!=shell.get('combination_ref'):continue
                if exclusion_live(local,row):
                    checked.append(['excluded',row['exclusion_ref']]);reason='COMBINATION_EXCLUDED';break
            if reason:break
    result={'job_ref':job['job_ref'],'generation_ref':driver.generation_ref,
            'checks':checked,'check_complete':reason is None,'reason':reason,
            'producer_complete':False,'structure_complete':False}
    result['check_ref']='structural-check:'+digest(result)
    return result


def admitted(driver,job):
    if job['depth']<=3:return True
    return permit_for(driver,job) is not None


def permit_for(driver,job):
    try:chain={j['job_ref'] for j in ancestors(driver,job)}
    except ValueError:return None
    return next((w for w in driver.windows
        if w['generation_ref']==driver.generation_ref and w['root_job_ref'] in chain
        and w['first_depth']==driver.jobs[w['root_job_ref']]['depth']
        and w['first_depth']<=job['depth']<=w['last_depth']
        and w['last_depth']==w['first_depth']+2
        and w['permit_ref']=='structural-window:'+digest({k:v for k,v in w.items() if k!='permit_ref'})),None)


def authorize(driver,job,check):
    if (not check['check_complete'] or check['job_ref']!=job['job_ref']
            or check['generation_ref']!=driver.generation_ref
            or check['check_ref']!='structural-check:'+digest({k:v for k,v in check.items() if k!='check_ref'})):return None
    permit={'root_job_ref':job['job_ref'],'first_depth':job['depth'],'last_depth':job['depth']+2,
            'generation_ref':driver.generation_ref,'check_ref':check['check_ref']}
    permit['permit_ref']='structural-window:'+digest(permit)
    if not any(w['permit_ref']==permit['permit_ref'] for w in driver.windows):driver.windows.append(permit)
    driver.event(job,'window_authorized',permit=permit,check=check)
    return permit
