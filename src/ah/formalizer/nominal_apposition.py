"""One released apposition license, shared by proposal and write preparation."""
from .component_policy import compatible, _features
from .nominal_readings import heads, clean, variant, attested


def rules(cfg):
    return cfg.get('apposition_rules') or [dict(rule_id='LEGACY_NOMINATIVE',mode='NOMINATIVE',
                                               markers=cfg.get('apposition_markers',()))]


def agrees(dependent, host):
    return bool(dependent.cases & host.cases) and compatible(_features(dependent),_features(host))


def options(tokens, nominals, dependent, reading, cfg, quantities):
    if 'APPOSITION' not in cfg.get('dependency_senses',{}):return
    for rule in rules(cfg):
        markers=[t for t in tokens if t.end<=dependent.start and t.span in rule['markers']]
        if not markers:continue
        marker=markers[-1]
        for host in nominals:
            if host.end>marker.start:continue
            base=dict(kind='APPOSITION',host_ref=host.token_id,marker_ref=marker.token_id,
                      apposition_rule=rule['rule_id'],morph=clean(reading),variant=reading)
            if rule['mode']=='NOMINATIVE':
                if 'nom' in reading.cases:yield base
            else:
                for layer,hv in heads(host,quantities):
                    if agrees(reading,hv):yield {**base,'host_layer':layer,'host_morph':clean(hv)}


def licensed(state, evidence, dependent, cfg):
    d=dependent;marker=evidence.get(d.get('marker_ref'))
    rule=next((r for r in rules(cfg) if r['rule_id']==d.get('apposition_rule','LEGACY_NOMINATIVE')),None)
    if not rule or not marker or marker.span not in rule['markers']:return False
    if not evidence[d['host_ref']].end<=marker.start<marker.end<=evidence[d['head_ref']].start:return False
    reading=variant(d['morph'])
    if rule['mode']=='NOMINATIVE':return 'nom' in reading.cases
    host=d.get('host_morph')
    return bool(host and attested(state,d['host_ref'],host) and agrees(reading,variant(host)))
