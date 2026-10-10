"""Raw-input oracle binding. Fixtures contain language data, never gold outputs.

Live and replay runs use the same production ProviderAdapter. A replay transport
cannot send a request: missing durable reply bytes are an explicit failure.
"""
from copy import deepcopy
from dataclasses import asdict
from functools import lru_cache
from pathlib import Path
import http.client
import itertools, json, math, os, time, uuid
from urllib.parse import urlparse
from ah.llm.lmstudio_client import LMStudioClient
from ah.llm.ollama_client import OllamaClientError
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full, _observation
from ah.formalizer.pipeline import MorphProvider, t0
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.core.journal import JournalChannel
from ah.model.types import Hypernode, FunctionSymbol, Ref
from ah.model.operands import BoundVar, CountLiteral, TimeLiteral
from tools.formalizer_v7_test_support import test_release, role, sign_test_release
from tools.formalizer_v7_syntax_fixture import finite_clause_rules


_DEFAULT_MORPH_PROVIDER = MorphProvider
_oracle_morph_scope = None


class _OracleMorphCache:
    """Run-local dictionary analysis, without interpretation or store state.

    MorphProvider returns tuples of frozen MorphVariant records. Reusing those
    exact records retains every parse and its score; neither casing nor token
    spelling is normalized in the cache key. Dictionary loading is performed
    once per oracle execution instead of once per isolated AH case.
    """

    def __init__(self, provider):
        self.analyze = lru_cache(maxsize=4096)(provider.analyze)


def _oracle_morph(config):
    """Share only pure default morphology within one runner configuration.

    A new run owns a new CONFIG object. Keep at most its one dictionary/cache,
    and invalidate it when the provider factory changes. Custom or patched
    providers are constructed normally, since their purity is not established.
    AH, resource releases, selectors and interpretation evidence remain local
    to each case, and no model replies enter this cache.
    """
    global _oracle_morph_scope
    factory = MorphProvider
    if factory is not _DEFAULT_MORPH_PROVIDER:
        _oracle_morph_scope = None
        return factory()
    if (_oracle_morph_scope is None
            or _oracle_morph_scope[0] is not config
            or _oracle_morph_scope[1] is not factory):
        _oracle_morph_scope = (config, factory, _OracleMorphCache(factory()))
    return _oracle_morph_scope[2]

# Independently authored TEST_ONLY lexical fixture; not a reviewed production release.
# No expected case, case ID or source sentence is consulted in its construction.
LEXICON = (
 ('ARRIVE','прийти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('SLEEP','спать','STATE',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('READ','читать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('SEND','отправить','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'),('RECIPIENT','RECIPIENT','dat','ENTITY'))),
 ('TRANSFER','передать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'),('RECIPIENT','RECIPIENT','dat','ENTITY'))),
 ('PUT','положить','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'),('LOCATION','LOCATION','acc','ENTITY'))),
 ('LOCATIVE','быть','STATE',(('THEME','SUBJECT','nom','ENTITY'),('LOCATION','LOCATION','loc','ENTITY'))),
 ('LIE','лежать','STATE',(('THEME','SUBJECT','nom','ENTITY'),('LOCATION','LOCATION','loc','ENTITY'))),
 ('SAY','сказать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('CONTENT','OBJECT','acc','PROPOSITION'))),
 ('THINK','думать','STATE',(('AGENT','SUBJECT','nom','ENTITY'),('CONTENT','OBJECT','acc','PROPOSITION'))),
 ('BELIEVE','считать','STATE',(('AGENT','SUBJECT','nom','ENTITY'),('CONTENT','OBJECT','acc','PROPOSITION'))),
 ('WANT','хотеть','STATE',(('AGENT','SUBJECT','nom','ENTITY'),('CONTENT','OBJECT','acc','PROPOSITION'))),
 ('PROMISE','обещать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('RECIPIENT','RECIPIENT','dat','ENTITY'),('CONTENT','OBJECT','acc','PROPOSITION'))),
 ('ASK','просить','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('RECIPIENT','RECIPIENT','acc','ENTITY'),('CONTENT','OBJECT','acc','PROPOSITION'))),
 ('OPEN','открыть','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('STUDENT','студент','STATE',(('THEME','SUBJECT','nom','ENTITY'),)),
 ('PASS_EXAM','сдать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('LEAVE','уйти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('GO','идти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('DESTINATION','LOCATION','acc','ENTITY'))),
 ('SEE','видеть','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('ENTER','войти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('DOCTOR','врач','STATE',(('THEME','SUBJECT','nom','ENTITY'),)),
 ('TIRED','устать','STATE',(('EXPERIENCER','SUBJECT','nom','ENTITY'),)),
 ('SIT','сесть','TRANSITION',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('SIT_STATE','сидеть','STATE',(('THEME','SUBJECT','nom','ENTITY'),('LOCATION','LOCATION','loc','ENTITY'))),
 ('WORK','работать','PROCESS',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('SMOKE','курить','PROCESS',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('CALL','позвонить','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('RECIPIENT','RECIPIENT','dat','ENTITY'))),
 ('WRITE','написать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('MEET','встретить','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('ARRIVE_CITY','приехать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('DESTINATION','LOCATION','acc','ENTITY'))),
 ('DEPART_CITY','уехать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('SOURCE','SOURCE','gen','ENTITY'))),
 ('LIE_DOWN','лечь','TRANSITION',(('THEME','SUBJECT','nom','ENTITY'),('LOCATION','LOCATION','acc','ENTITY'))),
)
ENTITY_NAMES = {'иван':'ivan','пётр':'petr','петр':'petr','мария':'maria','маша':'maria',
 'сергей':'sergey','алексей':'alexey','книга':'book','стол':'table','полка':'shelf',
 'курьер':'courier','письмо':'letter','стул':'chair','окно':'window','москва':'moscow',
 'я':'speaker','ты':'addressee','экзамен':'exam'}

# These are explicit fixture declarations, not spelling-based identity rules.
# Each inflectional/aspectual entry has its own R-S ID. Its TemplateMap names
# an existing canonical T, so the release loader exercises real referential
# integrity even when two dictionary entries share a predicate representation.
LEXICAL_MAPPINGS = (
    ('SLEEP_ONSET', 'уснуть', 'SLEEP', 'TRANSITION'),
    ('READ_PERFECTIVE', 'прочитать', 'READ', 'EVENT'),
)

def fixture(core, profile):
    senses=[]; aliases={}
    for pred,lemma,mode,roles in LEXICON:
        rr=[]
        for _,rid,case,typ in roles:
            r=role(rid,(case,));r['argument_types']=[typ]
            # Optional roles remain explicitly optional, not made up by the model.
            if rid in {'RECIPIENT','LOCATION'}: r['cardinality']['min']=0;r['optionality']=True
            rr.append(r)
        senses.append((pred,lemma,'NOUN' if pred in {'STUDENT','DOCTOR'} else 'VERB',rr,'EVENT' if mode in {'PROCESS','TRANSITION'} else mode))
        aliases['fixture:T:'+pred]=(pred,{rid:name for name,rid,_,_ in roles})
    base=test_release(core,senses);m=deepcopy(base.manifest)
    R={r['kind']:r for r in m['entries']}
    modes={pred:mode for pred,lemma,mode,roles in LEXICON}
    for entry in R['R-V']['entries']:
        if modes[entry['sense_id']] in {'PROCESS','TRANSITION'}:entry['temporal_mode_hint']=modes[entry['sense_id']]
    for sense_id, lemma, target_sense, mode in LEXICAL_MAPPINGS:
        R['R-S']['entries'].append({'lemma':lemma,'POS':'VERB','sense_id':sense_id})
        valency=deepcopy(next(v for v in R['R-V']['entries'] if v['sense_id']==target_sense))
        valency.update(sense_id=sense_id,state_class='EVENT',temporal_mode_hint=mode)
        R['R-V']['entries'].append(valency)
        mapping=deepcopy(next(v for v in R['TemplateMap']['entries'] if v['sense_id']==target_sense))
        mapping['sense_id']=sense_id
        R['TemplateMap']['entries'].append(mapping)
    # Optional arguments require genuine T schemas for the retained role set.
    # Omitting LOCATION/RECIPIENT cannot silently map to a T that requires it.
    # This is a data-level combinator over the declared optional roles, not a
    # rule tied to an oracle sentence or its desired result.
    for valency in R['R-V']['entries']:
        optional=[r['role_id'] for r in valency['roles'] if r.get('optionality') and r['cardinality']['min']==0]
        full=next(m for m in R['TemplateMap']['entries'] if m['sense_id']==valency['sense_id'])
        target=core.store.get_template(full['template_ref'])
        pred,role_map=aliases[full['template_ref']]
        for size in range(1,len(optional)+1):
            for removed in itertools.combinations(optional,size):
                retained=tuple(r for r in target.roles if r.value not in removed)
                uid='fixture:T:optional:'+digest([full['template_ref'],[r.value for r in retained]])
                if not core.store.has_uid(uid):
                    from ah.model.types import Domain
                    core.add_template(Domain.C,target.predicate,retained,uid=uid)
                R['TemplateMap']['entries'].append({'sense_id':valency['sense_id'],'template_ref':uid,'roles':[r.value for r in retained]})
                aliases[uid]=(pred,{r.value:role_map[r.value] for r in retained})
    R['CorefPolicy']={'kind':'CorefPolicy','version':'test-v1','schema_version':'v7',
        'entries':[{'window_size':128,'hard_features':['gender','number','person','animacy'],
                    'ranking_criteria':['EXPLICIT_REF','SAME_SOURCE','RECENCY'],'tie_policy':'KEEP_ALL',
                    'event_anaphora_rules':[]}], 'dependency_versions':{}}
    m['entries'].append(R['CorefPolicy']);m['dependency_versions']['CorefPolicy']='test-v1'
    R['AttitudeMap']['entries']=[{'lemma':lemma,'argument_role':'OBJECT','holder_role':'SUBJECT','attitude':att,'factivity':False} for lemma,att in [('сказать','QUOTED'),('думать','EMBEDDED'),('считать','EMBEDDED'),('хотеть','HYPOTHETICAL'),('обещать','HYPOTHETICAL'),('просить','HYPOTHETICAL')]]
    # Ordinary conditionals and counterfactual conditionals are distinct
    # declared constructions, with mutually exclusive scope triggers. The
    # runtime still validates them through its generic required_operators path.
    R['ScopeLexicon']['entries']=[{'pattern':pattern,'operator':op} for pattern,op in [(r'\bне\b|\bневерно\b','NOT'),(r'\bили\b','OR'),(r'\bкажд\w*\b','FORALL'),(r'\bмож\w*\b|\bмог(?:ла|ло|ли)?\b|\bвозможно\b','POSSIBLE'),(r'\bесли\b(?!\s+бы\b)','IMPLIES'),(r'\bесли\s+бы\b','COUNTERFACTUAL')]]
    # The generic and explicit-continuity patterns are mutually exclusive.
    # An unspecified day does not acquire continuous truth from a fixture.
    R['TemporalRules']['entries']=[
        {'pattern':r'\bвчера\b|(?<!весь\s)\bвчерашний\s+день\b','kind':'DAY_INTERVAL','day_offset':-1,'interval_semantics':'EXISTENTIAL'},
        {'pattern':r'\bвесь\s+вчерашний\s+день\b','kind':'DAY_INTERVAL','day_offset':-1,'interval_semantics':'CONTINUOUS'},
        {'pattern':r'\bсегодня\b|(?<!весь\s)\bсегодняшний\s+день\b','kind':'DAY_INTERVAL','day_offset':0,'interval_semantics':'EXISTENTIAL'},
        {'pattern':r'\bвесь\s+сегодняшний\s+день\b','kind':'DAY_INTERVAL','day_offset':0,'interval_semantics':'CONTINUOUS'},
        {'pattern':r'\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b','kind':'POINT_CLOCK'}]
    if profile=='known_mapping_broken':
        R['R-S']['entries']=[r for r in R['R-S']['entries'] if r['sense_id']!='SEND']+[{'lemma':'отправить','POS':'VERB','sense_id':'K_SEND'}]
        for r in R['R-V']['entries']:
            if r['sense_id']=='SEND':r['sense_id']='K_SEND'
        R['TemplateMap']['entries']=[r for r in R['TemplateMap']['entries'] if r['sense_id']!='SEND']
    # pymorphy declares a finite verb as VERB and its infinitive as INFN.
    # R-S matching is intentionally exact on POS: declare each infinitive
    # reading independently, with its own sense ID and the same explicit T
    # mapping as its finite reading. This changes fixture data, not runtime
    # POS equivalence or sentence-specific control/inference rules.
    for finite in tuple(R['R-S']['entries']):
        if finite['POS']!='VERB':continue
        finite_id=finite['sense_id'];infinitive_id=finite_id+'_INFN'
        infinitive=deepcopy(finite)
        infinitive.update(POS='INFN',sense_id=infinitive_id)
        R['R-S']['entries'].append(infinitive)
        for valency in tuple(R['R-V']['entries']):
            if valency['sense_id']==finite_id:
                infinitive_valency=deepcopy(valency)
                infinitive_valency['sense_id']=infinitive_id
                R['R-V']['entries'].append(infinitive_valency)
        for mapping in tuple(R['TemplateMap']['entries']):
            if mapping['sense_id']==finite_id:
                infinitive_mapping=deepcopy(mapping)
                infinitive_mapping['sense_id']=infinitive_id
                R['TemplateMap']['entries'].append(infinitive_mapping)
    # Independently declared TEST_ONLY grammar, derived from the finalized
    # released dictionary/valencies. A rule must cover its entire sentence;
    # complex or ambiguous structures still take the ordinary bounded TP path.
    # No oracle ID, input sentence or expected answer enters this compilation.
    R['SyntaxRules']['entries']=finite_clause_rules({kind:resource['entries'] for kind,resource in R.items()})
    R['SyntaxRules']['dependency_versions']={'R-S':R['R-S']['version'],'R-V':R['R-V']['version']}
    R['ProposalPolicy']['entries'][0]['verify_deterministic']=False
    R['ProposalPolicy']['entries'][0]['max_rule_steps']=100000
    content={k:m[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
    m['coverage_report']['resource_content_sha256']=digest(content)
    m['coverage_report']['units_by_kind']={k:len(r['entries']) for k,r in R.items()}
    release,trusted=sign_test_release(m);release.validate_store(core.store)
    release._oracle_test_trust=trusted
    from ah.formalizer.graph_ops import ensure_entity
    for name in sorted(set(ENTITY_NAMES.values())):
        ensure_entity(core,{'uid':'fixture:language:M:'+name,'name':name})
    return release,aliases

def _provider_progress(event, **fields):
    """Progress is observational; an unavailable consumer cannot change inference."""
    try:
        from tools.formalizer_v7_progress import emit
        emit(event, **fields)
    except Exception:
        pass


def _observed_provider_stats(data):
    """Keep server measurements independently of the bounded raw preview.

    These numbers are observation only: no estimate or missing value is
    invented, and they are never fed back into interpretation or validation.
    """
    stats = data.get('stats') if isinstance(data, dict) else None
    if not isinstance(stats, dict):
        return {}
    fields = ('input_tokens', 'total_output_tokens', 'reasoning_output_tokens',
              'tokens_per_second', 'time_to_first_token_seconds')
    return {key: value for key in fields
            if type(value := stats.get(key)) in (int, float) and value >= 0
            and (type(value) is int or math.isfinite(value))}


class _OracleHTTPClient(LMStudioClient):
    """Shared request schema/parser, raw HTTP transport, and no endpoint fallback.

    Runtime's native-chat helper can retry a non-reasoning model without the
    reasoning flag. Oracle probes require an explicit off contract: transport
    failures use RuntimeError so that retry branch is never taken.
    """
    def __init__(self, config):
        super().__init__(config['base_url'], timeout_seconds=config.get('timeout',120),
                         api_key=os.environ.get('FORMALIZER_ORACLE_API_KEY',''))
        self.raw_response = ''
        self.http_status = None

    def _request(self, method, path, body=None):
        url = self.base_url + path
        parsed = urlparse(url)
        if parsed.scheme not in {'http','https'} or not parsed.hostname:
            raise RuntimeError('PROVIDER_BASE_URL_INVALID')
        if parsed.query or parsed.fragment or parsed.username or parsed.password:
            raise RuntimeError('PROVIDER_BASE_URL_INVALID')
        connection = http.client.HTTPSConnection if parsed.scheme == 'https' else http.client.HTTPConnection
        conn = connection(parsed.hostname, parsed.port or (443 if parsed.scheme=='https' else 80),
                          timeout=self.timeout_seconds)
        payload = None if body is None else json.dumps(body,ensure_ascii=False).encode('utf-8')
        headers = {'Accept':'application/json'}
        if payload is not None:
            headers['Content-Type']='application/json'
            headers['Content-Length']=str(len(payload))
        if self.api_key:headers['Authorization']='Bearer '+self.api_key
        try:
            # Keep raw http.client: some local proxies reject urllib's equivalent
            # request with 502. Preserve both HTTPS and reverse-proxy URL prefixes.
            conn.request(method, parsed.path or '/', body=payload, headers=headers)
            response=conn.getresponse()
            self.http_status=response.status
            self.raw_response=response.read().decode('utf-8','replace')
            if response.status != 200:
                raise RuntimeError(f'HTTP {response.status}: {response.reason} at {url}: '
                                   + self.raw_response[:500])
            try:data=json.loads(self.raw_response)
            except json.JSONDecodeError as exc:
                raise RuntimeError('PROVIDER_RESPONSE_INVALID_JSON') from exc
            if not isinstance(data,dict):raise RuntimeError('PROVIDER_RESPONSE_NOT_OBJECT')
            return data
        finally:
            conn.close()


class ChatBackend:
    """Stateless local protocol probes; explicit thinking off, never hidden text."""
    def __init__(self, config): self.config=config; self.model=config.get('model','')
    def generate(self,prompt,*,system='',role='',override=None):
        mode=self.config.get('provider','disabled')
        if mode=='replay':raise RuntimeError('REPLAY_BYTES_MISSING: network disabled')
        if mode=='disabled':raise RuntimeError('LOCAL_PROVIDER_DISABLED')
        if mode not in {'lmstudio','ollama','openai'}:raise RuntimeError('LOCAL_PROVIDER_UNSUPPORTED: '+str(mode))
        settings=override or {}
        client=_OracleHTTPClient(self.config)
        endpoint=client.base_url+({'lmstudio':'/api/v1/chat','ollama':'/api/chat',
                                   'openai':'/v1/chat/completions'}[mode])
        request_id=uuid.uuid4().hex
        started=time.perf_counter()
        _provider_progress('request_started',request_id=request_id,provider=mode,model=self.model,
                           role=role,endpoint=endpoint,prompt=str(prompt),system=str(system),
                           enable_thinking=False)
        text=None
        try:
            if mode=='lmstudio':
                data=client.native_chat(model=self.model,prompt=prompt,system=system,
                    temperature=settings.get('temperature',0),top_p=settings.get('top_p',1),
                    top_k=settings.get('top_k',0),repeat_penalty=settings.get('repeat_penalty',1),
                    max_tokens=settings.get('max_new_tokens',self.config.get('max_tokens',4096)),
                    reasoning='off')
                text=client.native_chat_text(data)
            elif mode=='ollama':
                # Match OllamaClient.chat's native request schema. Its historical
                # parser falls back to message.thinking; oracle protocol probes
                # instead require visible content and fail closed when absent.
                body={'model':self.model,'messages':[{'role':'system','content':system},
                      {'role':'user','content':prompt}], 'stream':False,'think':False,
                      'options':{'temperature':settings.get('temperature',0),
                          'top_p':settings.get('top_p',1),'top_k':settings.get('top_k',0),
                          'repeat_penalty':settings.get('repetition_penalty',settings.get('repeat_penalty',1)),
                          'num_predict':settings.get('max_new_tokens',self.config.get('max_tokens',4096))}}
                data=client._request('POST','/api/chat',body)
                if data.get('error'):
                    raise OllamaClientError('Ollama chat error: '+str(data['error']))
                message=data.get('message')
                if not isinstance(message,dict):
                    raise OllamaClientError('Ollama chat response missing message')
                content=message.get('content')
                if not isinstance(content,str) or not content.strip():
                    raise OllamaClientError('Ollama returned no visible message content; '
                                            'hidden thinking is not a protocol answer')
                if data.get('done') is False:
                    raise OllamaClientError('Ollama chat response incomplete')
                text=content.strip()
            else:
                body={'model':self.model,'messages':[{'role':'system','content':system},
                      {'role':'user','content':prompt}],
                      'temperature':settings.get('temperature',0),'top_p':settings.get('top_p',1),
                      'max_tokens':settings.get('max_new_tokens',self.config.get('max_tokens',4096)),
                      'stream':False,'store':False,'enable_thinking':False,
                      'chat_template_kwargs':{'enable_thinking':False}}
                data=client._request('POST','/v1/chat/completions',body)
                # Typed reasoning parts are not visible assistant content. The
                # shared parser never reads message.reasoning/reasoning_content.
                visible=deepcopy(data)
                choices=visible.get('choices')
                if isinstance(choices,list) and choices and isinstance(choices[0],dict):
                    message=choices[0].get('message')
                    if isinstance(message,dict) and isinstance(message.get('content'),list):
                        message['content']=[p for p in message['content'] if isinstance(p,dict)
                            and p.get('type') in {'text','output_text'}]
                text=client.chat_text(visible)
        except Exception as exc:
            _provider_progress('request_finished',request_id=request_id,status='ERROR',
                provider=mode,model=self.model,role=role,endpoint=endpoint,
                elapsed_seconds=time.perf_counter()-started,http_status=client.http_status,
                raw_response=client.raw_response,error=str(exc))
            raise
        stats = _observed_provider_stats(data) if mode == 'lmstudio' else {}
        _provider_progress('request_finished',request_id=request_id,status='SUCCESS',
            provider=mode,model=self.model,role=role,endpoint=endpoint,
            elapsed_seconds=time.perf_counter()-started,http_status=client.http_status,
            raw_response=client.raw_response,response=text,
            **({'provider_stats': stats} if stats else {}))
        return text

def json_safe(value):
    return json.loads(json.dumps(value,ensure_ascii=False,default=lambda x:sorted(x) if isinstance(x,(set,frozenset)) else str(x)))


def native_coverage(state,release,store):
    """Read the sealed native structures; do not infer coverage from factivity.

    The public native state currently exposes frames/decisions rather than a
    CoverageStatus field. This projection passes observed span sets to the
    production coverage function and exports those inputs for review. A query
    can therefore have full structure while adding no asserted fact.
    """
    from ah.formalizer.candidate_ir import compute_coverage
    covered=set(); open_lexical=False; surface_roles=0; closed_frames=[]; blocked_frames=[]
    for frame in state.frames:
        decision=state.decisions.get(frame.frame_id+'|predicate_value')
        selected=frame.semantic.get('candidate_specs',{}).get(decision.selected[0]) if decision and len(decision.selected)==1 else None
        closed=bool(selected and decision.outcome=='RESOLVED' and not frame.semantic.get('structural_unresolved'))
        if selected and selected['sense_kind']=='KNOWN':
            roles=set(selected['roles'].values())|set(frame.semantic.get('proposition_args',{}))
            mappings=[m for m in release.entries('TemplateMap') if m['sense_id']==selected['sense_id'] and set(m['roles'])==roles]
            closed &= bool(len(mappings)==1 and store.has_uid(mappings[0]['template_ref'])
                           and {r.value for r in store._store.get_template(mappings[0]['template_ref']).roles}==roles)
        if closed:
            closed_frames.append(frame.frame_id)
            covered.update(e.token_id for e in state.evidence
                           if frame.source_range[0]<=e.start and e.end<=frame.source_range[1])
            open_lexical |= selected['sense_kind']=='OPEN_LEXICAL'
            surface_roles += sum(r=='SURFACE_ARG' for r in selected['roles'].values())
        else:blocked_frames.append(frame.frame_id)
    for root in state.logical_roots:covered.update(root.get('alignment_refs',()))
    relevant={e.token_id for e in state.evidence if e.span.strip()
              and not (e.variants and all(v.pos=='PNCT' or 'PNCT' in v.features for v in e.variants))}
    unresolved=relevant-covered
    status=compute_coverage(tuple(sorted(covered)),tuple(sorted(unresolved)),surface_roles,
                            open_lexical,bool(closed_frames or state.logical_roots))
    return asdict(status),{'closed_frame_ids':closed_frames,'blocked_frame_ids':blocked_frames,
        'relevant_token_refs':sorted(relevant),'grammar_search_incomplete':state.grammar_search_incomplete}


def native_generation(state):
    """Export actual candidate trees and selected modes without gold tags."""
    modes=[]; candidates=[]; trees=[]
    for frame in state.frames:
        decision=state.decisions.get(frame.frame_id+'|predicate_value')
        selected=frame.semantic.get('candidate_specs',{}).get(decision.selected[0]) if decision and len(decision.selected)==1 else None
        if selected:modes.append({'frame_id':frame.frame_id,'mode':selected['state_class']})
        candidates.append({'frame_id':frame.frame_id,'source_range':list(frame.source_range),
            'lexical_units':json_safe(frame.semantic.get('lexical_units',{})),
            'proposed_roles':dict(frame.semantic.get('proposed_roles',{})),
            'proposition_args':json_safe(frame.semantic.get('proposition_args',{}))})
        for tree in frame.semantic.get('operator_forest',()):
            if tree not in trees:trees.append(tree)
    for tree in state.logical_roots:
        if tree not in trees:trees.append(tree)
    def count_operator(tree,name):
        return int(tree.get('operator')==name)+sum(count_operator(c,name) for c in tree.get('operands',()))
    return {'gold_patterns':[x for x in state.syntax_trace if str(x.get('coverage_tag','')).upper().startswith('GOLD')],
        'event_frame_count':sum(x['mode'] in {'EVENT','PROCESS','TRANSITION'} for x in modes),
        'frame_modes':modes,'structural_candidates':candidates,'operator_forest':json_safe(trees),
        'forall_count':sum(count_operator(t,'FORALL') for t in trees),
        'coordination_kind':'PREDICATE_GROUP' if any(t.get('operator')=='AND' for t in trees) else None}


def entities_in(formula):
    if not isinstance(formula,dict):return set()
    if 'entity' in formula:return {formula['entity']}
    return set().union(*(entities_in(value) for value in formula.get('roles',{}).values()),
                       *(entities_in(value) for value in formula.get('operands',())),
                       *(entities_in(value) for value in formula.get('group',())))


def native_candidate_patterns(session,state,release,limit=1024):
    """Project verified TP/grammar candidates, including nonfactive inputs.

    ``gold_patterns`` is a historical observer field name. Its contents are
    actual candidate patterns, never the gold corpus or committed-fact copies.
    Frames exist before seal, candidate_specs are the released T3 closed set,
    and entity bindings are the actual grounded TD result. Thus a QUERY may
    retain the same candidate as an ASSERTION while writing no support.
    """
    frames={f.frame_id:f for f in state.frames};evidence={e.token_id:e for e in state.evidence}
    sources=[];truncated=False
    def combinations(values):
        nonlocal truncated
        for i,parts in enumerate(itertools.product(*values)):
            if i>=limit:truncated=True;break
            yield parts
    def bound(value):
        return {'bound_var':session.native_variable_aliases.get(value,str(value))}
    def entity(frame,tid):
        if tid in frame.semantic.get('bound_arguments',{}):return bound(frame.semantic['bound_arguments'][tid])
        mention=frame.semantic.get('lexical_units',{}).get(tid,{}).get('mention_ref',tid)
        if mention in state.observation.get('unresolved_references',()):return None
        uid=state.observation.get('entity_bindings',{}).get(mention)
        if uid is not None:
            return decode_native(session,uid) if session.core.store.has_uid(uid) else {'entity_ref':uid}
        # A local ENTITY hypothesis remains a typed local reference until C.
        # Its source occurrence is retained, rather than linked by spelling.
        return {'entity_ref':'M:'+digest([state.source_uid,mention])}
    def frame_patterns(fid,active):
        if fid in active:return []
        frame=frames[fid];active=active|{fid};results=[]
        for candidate_id,spec in sorted(frame.semantic.get('candidate_specs',{}).items()):
            role_ids=set(spec['roles'].values())|set(frame.semantic.get('proposition_args',{}))
            if spec['sense_kind']=='KNOWN':
                mappings=[m for m in release.entries('TemplateMap') if m['sense_id']==spec['sense_id'] and set(m['roles'])==role_ids]
                if len(mappings)!=1 or mappings[0]['template_ref'] not in session.native_aliases:continue
                pred,role_map=session.native_aliases[mappings[0]['template_ref']]
            else:
                unit=frame.semantic.get('lexical_units',{}).get(frame.predicate_token_ref,{})
                ev=evidence[frame.predicate_token_ref]
                label=unit.get('surface') if len(unit.get('anchor_refs',()))>1 else ev.lemma or ev.span
                pred='OPEN:'+label
                role_map={r:{'SUBJECT':'AGENT','OBJECT':'THEME'}.get(r,r) for r in role_ids}
            roles={};valid=True
            for tid,rid in spec['roles'].items():
                value=entity(frame,tid)
                if value is None:valid=False;break
                key=role_map.get(rid,rid)
                if key in roles:
                    if rid!='SURFACE_ARG':valid=False;break
                    previous=roles[key]
                    roles[key]={'group':[*previous['group'],value]} if 'group' in previous else {'group':[previous,value]}
                else:roles[key]=value
            if not valid:continue
            children=[];keys=[]
            for rid,child in frame.semantic.get('proposition_args',{}).items():
                options=tree_patterns(child.get('tree') or {'frame_ref':child['frame_ref']},active)
                if not options:valid=False;break
                keys.append(role_map.get(rid,rid));children.append(options)
            if not valid:continue
            sources.append({'frame_id':fid,'candidate_id':candidate_id,
                            'pattern_ids':list(frame.provenance.pattern_ids)})
            for parts in combinations(children):
                results.append({'predicate':pred,'roles':{**roles,**dict(zip(keys,parts))}})
        return results
    def tree_patterns(tree,active):
        if 'frame_ref' in tree:return frame_patterns(tree['frame_ref'],active)
        if 'bound_var' in tree:return [bound(tree['bound_var'])]
        if 'time_literal' in tree:return [{'time_literal':list(tree['time_literal'])}]
        if 'count_literal' in tree:return [{'count_literal':tree['count_literal']}]
        children=[tree_patterns(child,active) for child in tree.get('operands',())]
        if not tree.get('operator') or any(not options for options in children):return []
        results=[]
        for parts in combinations(children):
            operands=list(parts)
            if tree['operator'] in {'AND','OR','XOR'}:operands.sort(key=lambda v:json.dumps(v,sort_keys=True))
            results.append({'operator':tree['operator'],'operands':operands})
        return results
    patterns=[];trees=list(state.logical_roots)
    for frame in state.frames:
        patterns.extend(frame_patterns(frame.frame_id,set()))
        for tree in frame.semantic.get('operator_forest',()):
            if tree not in trees:trees.append(tree)
    for tree in trees:patterns.extend(tree_patterns(tree,set()))
    return session.unique(patterns),session.unique(sources),truncated


def native_entity_refs(session):
    return {uid for domain in session.core.store._state.domains.values() for uid in domain
            if session.core.store.kind_of(uid).value=='M'}


def native_write_observations(session,state,entities_before):
    """Read actual writes and typed discourse-variable uses, including empty IR."""
    ledger=session.store.ledger
    instances={s['conclusion_ref'] for s in ledger.data['supports'].values()
               if s['kind']=='DERIVED' and s.get('rule_id')=='FORALL_INST'}
    evidence_refs={e.token_id for e in state.evidence}
    variable_uses={};trees=list(state.logical_roots)
    for frame in state.frames:
        for mention_ref,variable in frame.semantic.get('bound_arguments',{}).items():
            variable_uses.setdefault(variable,[]).append({'frame_id':frame.frame_id,'mention_ref':mention_ref})
        for tree in frame.semantic.get('operator_forest',()):
            if tree not in trees:trees.append(tree)
    existential_variables=set()
    def visit(tree):
        if tree.get('operator')=='EXISTS' and tree.get('operands') and 'bound_var' in tree['operands'][0]:
            existential_variables.add(tree['operands'][0]['bound_var'])
        for child in tree.get('operands',()):visit(child)
    for tree in trees:visit(tree)
    bound_mentions={r['mention_ref'] for uses in variable_uses.values() for r in uses}
    local_mentions={row['mention_ref'] for row in state.observation.get('local_reference_targets',{}).values()}
    created=sorted(native_entity_refs(session)-entities_before)
    fictitious=[]
    for uid in created:
        meta=session.core.store.get_element_any_domain(uid).meta
        mention=meta.get('mention_ref')
        if mention in bound_mentions or mention not in evidence_refs|local_mentions:
            fictitious.append(uid)
    return {'forall_instance_count':len(instances),'fictitious_entities':fictitious,
            'created_entity_refs':created}, {
        'discourse_variable':bool(existential_variables & set(variable_uses)),
        'discourse_variable_uses':{str(variable):uses for variable,uses in sorted(variable_uses.items())},
        'existential_variable_ids':sorted(existential_variables)}

def execute_native(session,p,config):
    if not getattr(session,'native_ready',False):
        # Fresh fixture core is the same actual AH core owned by the session.
        session.release,session.native_aliases=fixture(session.core,p.get('resource_profile','known'))
        session.entities.update({'fixture:language:M:'+name:name for name in set(ENTITY_NAMES.values())})
        from tools import formalizer_v7_runtime_adapter as base
        if base.RESOURCE_ARTIFACT_DIR:
            dest=Path(base.RESOURCE_ARTIFACT_DIR);dest.mkdir(parents=True,exist_ok=True)
            (dest/(session.release.sha256+'.json')).write_text(json.dumps(session.release.manifest,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
            (dest/(session.release.sha256+'.trust.json')).write_text(json.dumps(session.release._oracle_test_trust,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf-8')
        session.native_ready=True;session.initial_snapshot=digest(session.store._codec.export(session.core))
        session.bootstrap=session.store._codec.export(session.core)
    release=session.release
    raw=deepcopy(p.get('raw_input') or {'text':p['text'], 'source_id':'fixture:partial',
        'revision':1,'range':[0,len(p['text'])],'language':'ru','request_kind':'MIXED','batch_kind':'MESSAGE'})
    text=raw['text'];morph=_oracle_morph(config)
    raw.setdefault('time_anchor',raw.get('source_timestamp'));raw.setdefault('timezone','UTC')
    # Explicit fixture identity bindings, never production name-based linking.
    bindings={}
    binding_evidence=t0(text).evidence
    binding_variants={ev.token_id:morph.analyze(ev.span) for ev in binding_evidence}
    for ev in binding_evidence:
        names={ENTITY_NAMES.get(v.lemma) for v in binding_variants[ev.token_id]}-{None}
        if len(names)==1:
            alias=names.pop();uid='fixture:language:M:'+alias
            if not session.core.store.has_uid(uid):
                from ah.formalizer.graph_ops import ensure_entity
                ensure_entity(session.core,{'uid':uid,'name':alias})
            bindings[ev.token_id]=uid;session.entities[uid]=alias
    # Explicit TEST_ONLY binding carriers for the independent lexical pattern
    # [PREP, declared entity]. A validated TP unit may include its preposition;
    # its full-span mention ID then differs from the noun's token ID. Declare
    # that carrier before inference instead of teaching the production planner
    # to equate arbitrary multiword mentions with their heads. Other compound
    # mentions receive no inferred identity, and no model reply/gold is read.
    for preposition,head in zip(binding_evidence,binding_evidence[1:]):
        if (head.token_id in bindings
                and any(v.pos=='PREP' for v in binding_variants[preposition.token_id])
                and any(v.pos in {'NOUN','NPRO'} for v in binding_variants[head.token_id])):
            mention_ref='mention:'+digest([preposition.token_id,head.token_id])
            bindings[mention_ref]=bindings[head.token_id]
    raw['entity_bindings']=bindings
    raw.setdefault('user_ref','fixture:language:M:speaker')
    raw.setdefault('self_ref','fixture:language:M:addressee')
    version=raw.get('interpretation_version',1)
    observation=_observation(text,version=version,raw_input=raw)
    run_id='native:'+digest([observation['observation_id'],version])
    selector=RealBackendSelector(ChatBackend(config),journal=session.store._journal,run_id=run_id,
        model_key=config.get('model') or 'disabled',generation_settings={'temperature':0.0,'top_p':1.0,'max_new_tokens':config.get('max_tokens',4096),'enable_thinking':False},
        structure_reply_format=config.get('structure_reply_format','TP-C2'),
        selection_reply_format=config.get('selection_reply_format','SELECT_LABELS_V1'))
    entities_before=native_entity_refs(session)
    state,report=interpret_full(text,None,selector,session.store,InterpretationRunBinding(session.store._journal),
        morph=morph,release=release,raw_input=raw,version=version,run_id=run_id)
    session.api.update({'v7_pipeline.interpret_full','native_frontend.run_native','RealBackendSelector / ProviderAdapter / ProviderCallLog','candidate_ir.compute_coverage'})
    session.native_states=getattr(session,'native_states',[])+[json_safe(asdict(state))]
    session.native_reports=getattr(session,'native_reports',[])+[json_safe(asdict(report))]
    session.sources[raw['source_id']]=[state.source_uid,state.interpretation_version]
    L=session.store.ledger; visible=L.f_visible()
    # Observer names for alpha-bound variables are assigned from actual typed
    # operands, independently of any expected formula. Raw local IDs remain
    # available in runtime.variable_bindings and the exported native IR.
    variable_ids=set()
    for node_id,node in L.data['nodes'].items():
        obj=session.core.store.get_element_any_domain(node_id)
        operands=obj.operands if isinstance(obj,FunctionSymbol) else obj.actants.values() if isinstance(obj,Hypernode) else ()
        variable_ids.update(v.local_id for v in operands if isinstance(v,BoundVar))
    variable_ids.update(value for frame in state.frames for value in frame.semantic.get('bound_arguments',{}).values())
    session.native_variable_aliases={value:('x','y','z')[i] if i<3 else 'v'+str(i)
                                     for i,value in enumerate(sorted(variable_ids))}
    session.native_lexical_labels=getattr(session,'native_lexical_labels',{})
    evidence={e.token_id:e for e in state.evidence}
    for node_id,node in L.data['nodes'].items():
        if node.get('semantic_status')=='UNLINKED' and node.get('source_tag')==[state.source_uid,state.interpretation_version]:
            ev=evidence.get(node.get('source_ref'))
            if ev and ev.lemma:session.native_lexical_labels[node_id]=ev.lemma
    facts=session.unique([decode_native(session,uid) for uid in visible])
    # IR is exported separately; this asserted view uses actual T5 eligibility,
    # not all generated parser hypotheses as facts.
    admitted=set(report.node_refs)
    rows=session.store._journal.scan_unprocessed(0)
    root=[s for s in L.data['supports'].values() if s['kind']=='ROOT']
    structural=session.unique([decode_native(session,uid) for uid in L.s_accessible()-visible])
    open_nodes=[n for n in L.data['nodes'].values() if n.get('semantic_status')=='UNLINKED']
    source=[a for a in L.data['assertions'].values() if a['provenance']['source']['kind']=='OBSERVATION']
    from ah.formalizer.speech_act import detect_speech_act
    from ah.logic.function_registry import FunctionRegistry
    readings=detect_speech_act(text,tuple(raw.get('context_facts',())))
    requested=raw.get('request_kind')
    imperative=any(v.mood=='imperative' for e in state.evidence for v in e.variants)
    modus=requested if requested in {'QUERY','COMMAND','UNKNOWN'} else 'AMBIGUOUS' if len(readings)>1 else 'COMMAND' if imperative else readings[0].kind
    derived=[s for s in L.data['supports'].values() if s['kind']=='DERIVED']
    semantics=[a['region'].get('kind') for a in source]
    registry=FunctionRegistry()
    registered={spec.function_id for spec in registry.items()}
    coverage,coverage_evidence=native_coverage(state,release,session.store)
    generation=native_generation(state)
    patterns,pattern_sources,truncated=native_candidate_patterns(session,state,release)
    generation.update(gold_patterns=patterns,observed_candidate_patterns=patterns,
                      candidate_pattern_sources=pattern_sources,pattern_export_truncated=truncated)
    groups=[f for f in facts if any(isinstance(v,dict) and 'group' in v for v in f.get('roles',{}).values())]
    if groups:generation['coordination_kind']='NOMINAL_GROUP'
    decisions=[{'frame_id':d.frame_id,'slot_id':d.slot_id,'outcome':d.outcome,
                'selected':list(d.selected),'candidate_ids':list(d.candidates)} for d in state.decisions.values()]
    predicate_decisions=[d for d in decisions if d['slot_id']=='predicate_value']
    decision_outcomes={d['outcome'] for d in predicate_decisions}
    # Match observation-source assertions against the temporal parser output,
    # not merely the presence of a timestamp. A source timestamp alone is never
    # permission to invent an interval from tense or an infinitive.
    from ah.formalizer.native_frontend import _temporal
    parsed_regions=[]
    for frame in state.frames:
        start,end=frame.source_range
        parsed,codes=_temporal(state.text[start:end],state.observation,release)
        if parsed is not None and not codes and parsed not in parsed_regions:parsed_regions.append(parsed)
    parsed,codes=_temporal(state.text,state.observation,release)
    if parsed is not None and not codes and parsed not in parsed_regions:parsed_regions.append(parsed)
    from ah.formalizer.canonical_ledger import region,region_data
    allowed_regions={digest(region_data(region(value))) for value in parsed_regions}
    invented=[a for a in source if a['provenance']['source'].get('source_tag')==[state.source_uid,state.interpretation_version]
              and digest(region_data(region(a['region']))) not in allowed_regions]
    writes,bindings_observed=native_write_observations(session,state,entities_before)
    from ah.formalizer.inference_policy import node_inference_policy
    return {'assertions':{'ah':facts,'ir':session.unique([decode_native(session,u) for u in admitted]),
            'journal':session.unique([decode_native(session,u) for u in admitted])},
        'supports':{'root_targets':[{'formula':decode_native(session,s['conclusion_ref'])} for s in root], 'root_count':len(root),'derived_rules':[s['rule_id'] for s in derived]},
        'structural':{'formulas':structural,'operator_formulas':[f for f in structural if 'operator' in f],
            'entity_aliases':sorted(set().union(*(entities_in(f) for f in structural)))},
        'diagnostics':{'codes':sorted({d.code for d in state.diagnostics})},
        'coverage':{'status':coverage['level'],**coverage,
            'opaque_full_claim':bool(coverage['level'] in {'FULL_CANONICAL','OPEN_LEXICAL'} and not generation['structural_candidates'] and not generation['operator_forest'])},
        'audit':{'raw_input_retained':state.text==text},
        'modus':modus,
        'goal':{'non_factive':not facts and modus in {'COMMAND','QUERY','AMBIGUOUS','UNKNOWN'}},
        'open':{'semantic_status':open_nodes[0]['semantic_status'] if open_nodes else None,
            'capabilities':sorted({cap for n in open_nodes for cap in
                node_inference_policy(n).capabilities})},
        'aliases':json_safe(list(L.data.get('template_links',{}).values())),
        'decision':{'outcome':next(iter(decision_outcomes)) if len(decision_outcomes)==1 else None,'records':decisions},
        'bindings':bindings_observed,
        'runtime':{'report':json_safe(asdict(report)),'ir':json_safe(asdict(state)),
            'coverage_evidence':coverage_evidence,
            'variable_bindings':{str(k):v for k,v in session.native_variable_aliases.items()},
            'provider_call_count':len([r for r in rows if r['payload'].get('kind')=='prov_call' and r['payload'].get('state')=='RECEIVED'])},
        'generation':generation,
        'time':{'invented_past_intervals':invented,'clock_default_used':False},
        'time_assertions':{'count':len(source),'records':source,'semantics':semantics},
        'store':{**writes,'new_record_count':len(L.data['nodes'])+len(L.data['supports']), 'marker_count':len(L.data['markers']),
            'unregistered_functions':[n.get('function_id') for n in L.data['nodes'].values() if n.get('kind')=='G' and registered and n.get('function_id') not in registered]}}

def decode_native(session,uid):
    if isinstance(uid,Ref):uid=uid.uid
    if isinstance(uid,BoundVar):return {'bound_var':getattr(session,'native_variable_aliases',{}).get(uid.local_id,str(uid.local_id))}
    if isinstance(uid,CountLiteral):return {'count_literal':uid.value}
    if isinstance(uid,TimeLiteral):return {'time_literal':list(uid.bounds)}
    if uid in session.entities:return {'entity':session.entities[uid]}
    obj=session.core.store.get_element_any_domain(uid)
    if isinstance(obj,Hypernode):
        if obj.template.uid in session.native_aliases:
            pred,role_map=session.native_aliases[obj.template.uid]
        else:
            spec=session.store.ledger.data['nodes'].get(uid,{})
            template=obj.meta
            label=getattr(session,'native_lexical_labels',{}).get(uid) or template.get('lexical_anchor') or template.get('lemma') or template.get('surface')
            if not label:
                # Read open isolation metadata rather than guessing a gold word.
                symbol=session.core.store.get_symbol(session.core.store.get_template(obj.template.uid).predicate.uid)
                label=sorted(symbol.forms)[0] if symbol.forms else obj.template.uid
            pred='OPEN:'+str(label);role_map={r.value: {'SUBJECT':'AGENT','OBJECT':'THEME'}.get(r.value,r.value) for r in obj.actants}
        return {'predicate':pred,'roles':{role_map.get(r.value,r.value):decode_native(session,v) for r,v in obj.actants.items()}}
    if isinstance(obj,FunctionSymbol):
        operands=[decode_native(session,v) for v in obj.operands]
        if obj.function_id in {'AND','OR','XOR'}:operands.sort(key=lambda v:json.dumps(v,sort_keys=True))
        return {'operator':obj.function_id,'operands':operands}
    if hasattr(obj,'members'):return {'group':[decode_native(session,v) for v in obj.members]}
    return {'unbound_ref':uid,'kind':session.core.store.kind_of(uid).value}
