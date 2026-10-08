"""Resource preparation on actual AH references and a fixed external corpus."""
from __future__ import annotations
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from .loader import ResourceRelease
from .schemas import candidate_schema_entries


def load_store(path):
    from ah.core.persistence import JsonPersistence
    from ah.config import PersistenceSettings
    return JsonPersistence(path, PersistenceSettings()).load().core.store


def build_release(directory, *, version, store):
    """Use authored containers; never derive senses or equivalences from names."""
    resources=[]
    for path in sorted(Path(directory).glob('*.json')):
        resource=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(resource,dict) or 'kind' not in resource:
            raise ValueError('resource file is not a container: '+str(path))
        resources.append(resource)
    if not any(r['kind']=='CandidateSchema' for r in resources):
        resources.append({'kind':'CandidateSchema','version':'emit-v1','schema_version':'v7',
                          'entries':candidate_schema_entries(),'dependency_versions':{}})
    manifest={'kind':'FORMALIZER_RESOURCE_RELEASE','version':version,'schema_version':'v7',
              'entries':sorted(resources,key=lambda r:r['kind']),
              'dependency_versions':{r['kind']:r['version'] for r in resources}}
    release=ResourceRelease(manifest,require_review=False)
    release.validate_store(store)
    return manifest


def resource_coverage(release, corpus_path):
    """Measure lexical resource availability, independently of behavior/PASS."""
    import pymorphy3
    blob=Path(corpus_path).read_bytes()
    corpus=json.loads(blob.decode('utf-8'))
    if (not isinstance(corpus,dict) or set(corpus)!={'corpus_id','units'}
            or not isinstance(corpus['corpus_id'],str) or not corpus['corpus_id']
            or not isinstance(corpus['units'],list) or not corpus['units']):
        raise ValueError('corpus requires corpus_id and nonempty units[{unit_id,text}]')
    ids=set(); morph=pymorphy3.MorphAnalyzer(); counts=Counter(); measured=[]
    senses={}
    for row in release.entries('R-S'):
        senses.setdefault((row['lemma'],row['POS']),set()).add(row['sense_id'])
    mapped={r['sense_id'] for r in release.entries('TemplateMap')}
    valencies={r['sense_id'] for r in release.entries('R-V')}
    for unit in corpus['units']:
        if (not isinstance(unit,dict) or set(unit)!={'unit_id','text'} or not isinstance(unit['unit_id'],str)
                or not unit['unit_id'] or unit['unit_id'] in ids or not isinstance(unit['text'],str)):
            raise ValueError('invalid/duplicate corpus unit')
        ids.add(unit['unit_id'])
        for match in re.finditer(r'\w+',unit['text']):
            word=match[0]; parses=morph.parse(word)
            values=set().union(*(senses.get((p.normal_form,p.tag.POS),set()) for p in parses))
            if values:
                category='COVERED' if values <= mapped & valencies else 'NOT_COVERED'
            else:
                category='KNOWLEDGE_ABSENT' if morph.word_is_known(word) else 'OOV_KEEP_AS_IS'
            counts[category]+=1
            measured.append({'unit_id':unit['unit_id'],'range':[match.start(),match.end()],
                             'surface':word,'category':category})
    units={kind:len(resource['entries']) for kind,resource in release.resources.items()}
    units['R-V']=len({(r.get('lemma'),r.get('POS'),r['sense_id']) for r in release.entries('R-V')})
    units['R-S']=len({(r['lemma'],r['POS'],r['sense_id']) for r in release.entries('R-S')})
    units['TemplateMap']=len({(r['sense_id'],r['template_ref']) for r in release.entries('TemplateMap')})
    units['SyntaxRules']=len(release.entries('SyntaxRules'))
    units['ScopeLexicon']=len({r['pattern'] for r in release.entries('ScopeLexicon')})
    return {'corpus_id':corpus['corpus_id'],'corpus_sha256':hashlib.sha256(blob).hexdigest(),
            'units_by_kind':units,'categories':{k:counts[k] for k in ('COVERED','NOT_COVERED','KNOWLEDGE_ABSENT','OOV_KEEP_AS_IS')},
            'measurement_kind':'RESOURCE_LEXICAL_AVAILABILITY','unit_count':len(ids),
            'resource_content_sha256':release.content_sha256,'measured_units':measured,'execution_coverage':None}


def template_catalog(store):
    """Export actual T references, without asserting sense mappings by name."""
    from ah.model import RefKind
    rows=[]
    for domain in store._state.domains.values():
        for uid,element in domain.items():
            if store.kind_of(uid) is not RefKind.T: continue
            rows.append({'template_ref':uid,'predicate_ref':element.predicate.uid,
                         'roles':[r.value for r in element.roles]})
    return {'kind':'AH_TEMPLATE_CATALOG','entries':sorted(rows,key=lambda r:r['template_ref'])}


def profile_experience(store,release,corpus_path,*,limit=4096):
    """Read an actual snapshot; no canonical writes, generated memory or tests."""
    from copy import deepcopy
    from ..canonical_ledger import CanonicalLedger
    from ..rx_observability import ExperienceIndex,lexical_keys
    if type(limit) is not int or not 1<=limit<=100000: raise ValueError('RX_LIMIT_INVALID')
    blob=Path(corpus_path).read_bytes(); corpus=json.loads(blob.decode('utf-8'))
    if not isinstance(corpus,dict) or set(corpus)!={'corpus_id','units'} or not isinstance(corpus['units'],list):
        raise ValueError('invalid fixed corpus')
    ledger=CanonicalLedger(deepcopy(store._state.formalizer_state)); ledger.validate_audit()
    index=ExperienceIndex(); index.build(ledger.data['rx_cache'],ledger.data.get('wal_seq',0))
    snapshot={'snapshot_id':release.sha256,'release_version':release.manifest['version']}; rows=[]; ids=set()
    for unit in corpus['units']:
        if (not isinstance(unit,dict) or set(unit)!={'unit_id','text'} or not isinstance(unit['unit_id'],str)
                or unit['unit_id'] in ids or not isinstance(unit['text'],str)): raise ValueError('invalid corpus unit')
        ids.add(unit['unit_id'])
        found,diag=index.read(ledger,snapshot,lexical_keys(unit['text']),limit)
        rows.append({'unit_id':unit['unit_id'],'stage_records':{s:len(v) for s,v in found.items()},'diagnostics':diag})
    return {**index.report(),'corpus_id':corpus['corpus_id'],'corpus_sha256':hashlib.sha256(blob).hexdigest(),
            'canonical_snapshot_sha256':digest_snapshot(store),'resource_snapshot':release.sha256,
            'memory_records':len(ledger.data['nodes']),'support_records':len(ledger.data['supports']),
            'units':rows,'semantic_benefit':None}


def digest_snapshot(store):
    from ..canonical_ledger import digest
    from ah.core.persistence import JsonPersistence
    from ah.config import PersistenceSettings
    from ah.core.operations import AHCore
    return digest(JsonPersistence(Path('unused-rx-profile.snapshot'),PersistenceSettings()).export(AHCore(store)))
