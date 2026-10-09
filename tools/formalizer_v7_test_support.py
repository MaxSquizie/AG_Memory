"""Isolated oracle fixtures. TEST_ONLY key/data must never be production defaults."""
from copy import deepcopy
from dataclasses import asdict
import base64, json
from ah.core.operations import AHCore
from ah.core.store import AHStore
from ah.core.journal import JournalChannel
from ah.model.types import ActantRole, Domain
from ah.formalizer.resources.loader import ResourceRelease
from ah.formalizer.resources.schemas import candidate_schema_entries
from ah.formalizer.resources.signatures import sign_review
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.store_interface import CommitDecision,MaterializationMarker,TerminalOutcome,JournalRecord


def sign_test_release(manifest):
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    from cryptography.hazmat.primitives.serialization import Encoding,PrivateFormat,NoEncryption,PublicFormat
    manifest=deepcopy(manifest)
    unsigned=ResourceRelease(manifest,require_review=False)
    key=Ed25519PrivateKey.from_private_bytes(bytes.fromhex('7f'*32)) # public test fixture seed
    review=sign_review(unsigned.sha256,reviewer='ORACLE_FIXTURE_ONLY',timestamp='2026-10-09T00:00:00+00:00',key_id='TEST_ONLY',private_key_pem=key.private_bytes(Encoding.PEM,PrivateFormat.PKCS8,NoEncryption()))
    manifest['signed_review_id']=review
    trusted={'keys':{'TEST_ONLY':{'reviewer':'ORACLE_FIXTURE_ONLY','public_key_b64':base64.b64encode(key.public_key().public_bytes(Encoding.Raw,PublicFormat.Raw)).decode()}},'reviews':{unsigned.sha256:review}}
    return ResourceRelease(manifest,trusted_reviews=trusted),trusted


def role(role_id,cases=('nom',)):
    return {'role_id':role_id,'allowed_cases':list(cases),'argument_types':['ENTITY'],'cardinality':{'min':1,'max':1},'optionality':False}


def test_release(core,senses=(),syntax=()):
    resources={k:[] for k in ResourceRelease.REQUIRED}
    resources['RoleRegistry']=[{'role_id':r.value} for r in ActantRole]
    resources['CandidateSchema']=candidate_schema_entries()
    resources['OpenTemplatePolicy']=[{'allow':True}]
    resources['ProposalPolicy']=[{'max_nodes':128,'max_edges':128,'max_depth':32,'max_source_tokens':256}]
    resources['SyntaxRules']=list(syntax)
    for raw in senses:
        sid,lemma,pos,roles,*mode=raw
        suid='fixture:S:'+sid;tuid='fixture:T:'+sid
        core.add_abstract_symbol({lemma+':'+sid},uid=suid)
        core.add_template(Domain.C,core.ref(suid),tuple(ActantRole(r['role_id']) for r in roles),uid=tuid)
        resources['R-S'].append({'lemma':lemma,'POS':pos,'sense_id':sid})
        resources['R-V'].append({'sense_id':sid,'roles':roles,'state_class':mode[0] if mode else 'STATE'})
        resources['TemplateMap'].append({'sense_id':sid,'template_ref':tuid,'roles':[r['role_id'] for r in roles]})
    entries=[{'kind':k,'version':'test-v1','schema_version':'v7','entries':v,'dependency_versions':{}} for k,v in sorted(resources.items())]
    manifest={'kind':'FORMALIZER_RESOURCE_RELEASE','version':'TEST_ONLY-v1','schema_version':'v7','entries':entries,'dependency_versions':{k:'test-v1' for k in resources}}
    manifest['coverage_report']={'corpus_id':'isolated-test-fixture-empty-lexical-sample','corpus_sha256':digest([]),'units_by_kind':{k:len(v) for k,v in resources.items()},'categories':{k:0 for k in ('COVERED','NOT_COVERED','KNOWLEDGE_ABSENT','OOV_KEEP_AS_IS')},'resource_content_sha256':digest(manifest),'measurement_kind':'RESOURCE_LEXICAL_AVAILABILITY','measured_units':[],'execution_coverage':None}
    release,_=sign_test_release(manifest);release.validate_store(core.store)
    return release

test_release.__test__=False


def binary_rule(rule_id,predicate_lemma,first='nom',second='acc'):
    return {'rule_id':rule_id,'input_feature_pattern':{'captures':{'p':{'lemma':[predicate_lemma],'POS':['VERB']},'a':{'POS':['NOUN','NPRO'],'cases':[first]},'b':{'POS':['NOUN'],'cases':[second]}}},'output_kind':'CANDIDATE_GRAPH','output':{'nodes':[{'id':k,'kind':kind,'anchors':[k]} for k,kind in [('p','PREDICATE'),('a','ENTITY'),('b','ENTITY')]],'edges':[{'kind':'ARGUMENT','from':'p','to':'a','role_id':'SUBJECT'},{'kind':'ARGUMENT','from':'p','to':'b','role_id':'OBJECT'}]},'constraints':[{'kind':'BEFORE','left':'a','right':'p'},{'kind':'BEFORE','left':'p','right':'b'}],'priority':0,'min_evidence':3,'coverage_tag':'TEST_ONLY'}


def native_fixture(path):
    core=AHCore(AHStore())
    senses=[(s,'быть','VERB',[role('SUBJECT',('gen',)),role('OBJECT',('nom',))],'STATE') for s in ('HAVE','HAVE_PART')]
    senses.append(('LIKE','любить','VERB',[role('SUBJECT'),role('OBJECT',('acc',))],'STATE'))
    release=test_release(core,senses,[binary_rule('TEST-HAVE','быть','gen','nom'),binary_rule('TEST-LIKE','любить')])
    journal=JournalChannel(path);store=AHStoreAdapter(core.store,journal,core)
    return store,InterpretationRunBinding(journal),release


class NativeSelector:
    def __init__(self,unresolved=False):self.unresolved=unresolved
    def propose(self,prompt):return None
    def select(self,prompt):
        section=prompt.split('closed set):\n',1)[1].split('\nTask:',1)[0]
        ids=[line.split('. ',1)[0] for line in section.splitlines() if '. ' in line]
        return json.dumps({'outcome':'MULTIPLE_ADMISSIBLE' if self.unresolved else 'ONE_SELECTED','selected':ids if self.unresolved else ids[:1]})


class FixtureMorph:
    def analyze(self,word):
        from ah.formalizer.state import MorphVariant
        lemma,pos,cases={'у':('у','PREP',()),'ивана':('иван','NOUN',('gen',)),'вороны':('ворона','NOUN',('gen',)),'есть':('быть','VERB',()),'книга':('книга','NOUN',('nom',))}.get(word.casefold(),(word.casefold(),'PNCT',()))
        return (MorphVariant(lemma=lemma,pos=pos,cases=frozenset(cases)),)


def journal_plan(store,ops,run_id='run-1',observation_id='obs1',version=2,batch_hash='h1',fragments=('F1',)):
    marker=MaterializationMarker(observation_id,version)
    decision=CommitDecision(run_id,batch_hash,marker,digest([asdict(op) for op in ops]),TerminalOutcome.APPLIED,committed=tuple(fragments))
    assert InterpretationRunBinding(store._journal).acquire(run_id,observation_id,version)
    payload={'kind':'BATCH','batch_hash':batch_hash,'ops':[asdict(op) for op in ops],'decision':{**asdict(decision),'outcome':decision.outcome.value}}
    store.append_journal('observation',JournalRecord('observation',run_id,payload))
    return decision
