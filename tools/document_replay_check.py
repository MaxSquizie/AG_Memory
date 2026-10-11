"""Verify native replay of an unchanged diagnostic source, not gold semantics."""
import json
from ah.documents.reading import read_document
from ah.formalizer.canonical_ledger import digest


def verify(services,source,out,first,backend,store):
    before={'calls':backend.ordinal,'tick':services.ignition.tick_index,
            'ledger':digest(store.ledger.data)}
    repeated=read_document(services,source,out/'reading_replay')
    after={'calls':backend.ordinal,'tick':services.ignition.tick_index,
           'ledger':digest(store.ledger.data)}
    def receipt(folder):
        return json.loads((out/folder/'interpretation.json').read_text(encoding='utf-8'))['commit_receipt']
    original,again=receipt('reading'),receipt('reading_replay')
    checks={'no_new_provider_calls':before['calls']==after['calls'],
            'no_new_ignition_ticks':before['tick']==after['tick'],
            'ledger_unchanged':before['ledger']==after['ledger'],
            'batch_hash_equal':original.get('batch_hash')==again.get('batch_hash'),
            'committed_fragments_equal':original.get('committed_fragments')==again.get('committed_fragments'),
            'both_executed':first['status']==repeated['status']=='EXECUTED'}
    result={'checks':checks,'passed':all(checks.values()),'before':before,'after':after,
            'semantic_correctness':'NOT_EVALUATED'}
    (out/'native_replay_check.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result['passed']
