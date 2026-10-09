"""Raw-input oracle binding. Fixtures contain language data, never gold outputs.

Live and replay runs use the same production ProviderAdapter. A replay transport
cannot send a request: missing durable reply bytes are an explicit failure.
"""
from copy import deepcopy
from dataclasses import asdict
import json, os, urllib.request, urllib.error
from ah.formalizer.canonical_ledger import digest
from ah.formalizer.real_backend import RealBackendSelector
from ah.formalizer.run_binding import InterpretationRunBinding
from ah.formalizer.v7_pipeline import interpret_full
from ah.formalizer.pipeline import MorphProvider, t0
from ah.formalizer.ah_adapter import AHStoreAdapter
from ah.core.journal import JournalChannel
from ah.model.types import Hypernode, FunctionSymbol, Ref
from ah.model.operands import BoundVar, CountLiteral, TimeLiteral
from tools.formalizer_v7_test_support import test_release, role, sign_test_release

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
 ('STUDENT','студент','STATE',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('PASS_EXAM','сдать','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('LEAVE','уйти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('GO','идти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('DESTINATION','LOCATION','acc','ENTITY'))),
 ('SEE','видеть','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),('THEME','OBJECT','acc','ENTITY'))),
 ('ENTER','войти','EVENT',(('AGENT','SUBJECT','nom','ENTITY'),)),
 ('DOCTOR','врач','STATE',(('THEME','SUBJECT','nom','ENTITY'),)),
 ('TIRED','устать','STATE',(('EXPERIENCER','EXPERIENCER','nom','ENTITY'),)),
 ('SIT_STATE','сидеть','STATE',(('THEME','SUBJECT','nom','ENTITY'),('LOCATION','LOCATION','loc','ENTITY'))),
 ('WORK','работать','PROCESS',(('AGENT','SUBJECT','nom','ENTITY'),)),
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
    R['AttitudeMap']['entries']=[{'lemma':lemma,'argument_role':'OBJECT','holder_role':'SUBJECT','attitude':att,'factivity':False} for lemma,att in [('сказать','QUOTED'),('думать','EMBEDDED'),('считать','EMBEDDED'),('хотеть','HYPOTHETICAL'),('обещать','HYPOTHETICAL'),('просить','HYPOTHETICAL')]]
    R['ScopeLexicon']['entries']=[{'pattern':pattern,'operator':op} for pattern,op in [(r'\bне\b|\bневерно\b','NOT'),(r'\bили\b','OR'),(r'\bкажд\w*\b','FORALL'),(r'\bмож\w*\b|\bвозможно\b','POSSIBLE'),(r'\bесли\b','IMPLIES')]]
    R['TemporalRules']['entries']=[{'pattern':r'\bвчера\b|\bвчерашн\w*\b','kind':'DAY_INTERVAL','day_offset':-1}, {'pattern':r'\bсегодня\b|\bсегодняшн\w*\b','kind':'DAY_INTERVAL','day_offset':0}, {'pattern':r'\b(?P<hour>\d{1,2}):(?P<minute>\d{2})\b','kind':'POINT_CLOCK'}]
    # TP is verified even when a deterministic structure exists. No special
    # sentence patterns are added to conceal structural omissions.
    R['ProposalPolicy']['entries'][0]['verify_deterministic']=True
    if profile=='known_mapping_broken':
        R['R-S']['entries']=[r for r in R['R-S']['entries'] if r['sense_id']!='SEND']+[{'lemma':'отправить','POS':'VERB','sense_id':'K_SEND'}]
        for r in R['R-V']['entries']:
            if r['sense_id']=='SEND':r['sense_id']='K_SEND'
        R['TemplateMap']['entries']=[r for r in R['TemplateMap']['entries'] if r['sense_id']!='SEND']
    content={k:m[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
    m['coverage_report']['resource_content_sha256']=digest(content)
    m['coverage_report']['units_by_kind']={k:len(r['entries']) for k,r in R.items()}
    release,_=sign_test_release(m);release.validate_store(core.store)
    return release,aliases

class ChatBackend:
    """OpenAI-compatible local server; no implicit external fallback."""
    def __init__(self, config): self.config=config; self.model=config.get('model','')
    def generate(self,prompt,*,system='',role='',override=None):
        mode=self.config.get('provider','disabled')
        if mode=='replay':raise RuntimeError('REPLAY_BYTES_MISSING: network disabled')
        if mode=='disabled':raise RuntimeError('LOCAL_PROVIDER_DISABLED')
        settings=override or {}
        body={'model':self.model,'messages':[{'role':'system','content':system},{'role':'user','content':prompt}],
              'temperature':settings.get('temperature',0),'top_p':settings.get('top_p',1),
              'max_tokens':settings.get('max_new_tokens',4096),'stream':False}
        url=self.config['base_url'].rstrip('/')
        if not url.endswith('/v1'):url+='/v1'
        headers={'Content-Type':'application/json'}
        key=os.environ.get('FORMALIZER_ORACLE_API_KEY')
        if key:headers['Authorization']='Bearer '+key
        req=urllib.request.Request(url+'/chat/completions',data=json.dumps(body,ensure_ascii=False).encode(),headers=headers)
        with urllib.request.urlopen(req,timeout=self.config.get('timeout',120)) as resp: data=json.load(resp)
        text=data['choices'][0]['message']['content']
        if not isinstance(text,str):raise ValueError('PROVIDER_RESPONSE_NOT_TEXT')
        return text

def json_safe(value):
    return json.loads(json.dumps(value,ensure_ascii=False,default=lambda x:sorted(x) if isinstance(x,(set,frozenset)) else str(x)))

def execute_native(session,p,config):
    if not getattr(session,'native_ready',False):
        # Fresh fixture core is the same actual AH core owned by the session.
        session.release,session.native_aliases=fixture(session.core,p.get('resource_profile','known'))
        session.native_ready=True;session.initial_snapshot=digest(session.store._codec.export(session.core))
        session.bootstrap=session.store._codec.export(session.core)
    release=session.release
    raw=deepcopy(p.get('raw_input') or {'text':p['text'], 'source_id':'fixture:partial',
        'revision':1,'range':[0,len(p['text'])],'language':'ru','request_kind':'MIXED','batch_kind':'MESSAGE'})
    text=raw['text'];morph=MorphProvider()
    raw['time_anchor']=raw.get('source_timestamp');raw['timezone']='UTC'
    # Explicit fixture identity bindings, never production name-based linking.
    bindings={}
    for ev in t0(text).evidence:
        names={ENTITY_NAMES.get(v.lemma) for v in morph.analyze(ev.span)}-{None}
        if len(names)==1:
            alias=names.pop();uid='fixture:language:M:'+alias
            if not session.core.store.has_uid(uid):
                from ah.formalizer.graph_ops import ensure_entity
                ensure_entity(session.core,{'uid':uid,'name':alias})
            bindings[ev.token_id]=uid;session.entities[uid]=alias
    raw['entity_bindings']=bindings
    raw.setdefault('user_ref','fixture:language:M:speaker')
    raw.setdefault('self_ref','fixture:language:M:addressee')
    run_id='native:'+digest([raw['source_id'],raw['revision'],raw['range']])
    selector=RealBackendSelector(ChatBackend(config),journal=session.store._journal,run_id=run_id,
        model_key=config.get('model') or 'disabled',generation_settings={'temperature':0.0,'top_p':1.0,'max_new_tokens':config.get('max_tokens',4096),'enable_thinking':False})
    state,report=interpret_full(text,None,selector,session.store,InterpretationRunBinding(session.store._journal),
        morph=morph,release=release,raw_input=raw,version=raw.get('interpretation_version',1),run_id=run_id)
    session.api.update({'v7_pipeline.interpret_full','native_frontend.run_native','RealBackendSelector / ProviderAdapter / ProviderCallLog'})
    session.native_states=getattr(session,'native_states',[])+[json_safe(asdict(state))]
    session.native_reports=getattr(session,'native_reports',[])+[json_safe(asdict(report))]
    L=session.store.ledger; visible=L.f_visible()
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
    return {'assertions':{'ah':facts,'ir':session.unique([decode_native(session,u) for u in admitted]),
            'journal':session.unique([decode_native(session,u) for u in admitted])},
        'supports':{'root_targets':[{'formula':decode_native(session,s['conclusion_ref'])} for s in root], 'root_count':len(root),'derived_rules':[s['rule_id'] for s in derived]},
        'structural':{'formulas':structural,'operator_formulas':[f for f in structural if 'operator' in f]},
        'diagnostics':{'codes':sorted({d.code for d in state.diagnostics})},
        'coverage':{'status':'OPEN_LEXICAL' if open_nodes else getattr(state,'coverage_status',None),
            'opaque_full_claim':False},
        'audit':{'raw_input_retained':state.text==text},
        'modus':modus,
        'goal':{'non_factive':not facts and modus in {'COMMAND','QUERY','AMBIGUOUS','UNKNOWN'}},
        'open':{'semantic_status':open_nodes[0]['semantic_status'] if open_nodes else None,
            'capabilities':sorted({cap for n in open_nodes for cap in (session.core.store.get_template(n['template_ref']).meta.get('inference_capabilities') or ())})},
        'aliases':[], 'runtime':{'report':json_safe(asdict(report)),'ir':json_safe(asdict(state)),
            'provider_call_count':len([r for r in rows if r['payload'].get('kind')=='prov_call' and r['payload'].get('state')=='RECEIVED'])},
        'generation':{'gold_patterns':[x for x in state.syntax_trace if str(x.get('coverage_tag','')).upper().startswith('GOLD')],
            'event_frame_count':len([f for f in state.frames if f.semantic.get('mode')=='EVENT'])},
        'time_assertions':{'count':len(source),'records':source,'semantics':semantics},
        'store':{'new_record_count':len(L.data['nodes'])+len(L.data['supports']), 'marker_count':len(L.data['markers']),
            'unregistered_functions':[n.get('function_id') for n in L.data['nodes'].values() if n.get('kind')=='G' and registered and n.get('function_id') not in registered]}}

def decode_native(session,uid):
    if isinstance(uid,Ref):uid=uid.uid
    if isinstance(uid,BoundVar):return {'bound_var':str(uid.local_id)}
    if isinstance(uid,CountLiteral):return {'count_literal':uid.value}
    if isinstance(uid,TimeLiteral):return {'time_literal':list(uid.bounds)}
    if uid in session.entities:return {'entity':session.entities[uid]}
    obj=session.core.store.get_element_any_domain(uid)
    if isinstance(obj,Hypernode):
        if obj.template.uid in session.native_aliases:
            pred,role_map=session.native_aliases[obj.template.uid]
        else:
            spec=session.store.ledger.data['nodes'].get(uid,{})
            template=session.core.store.get_template(obj.template.uid).meta
            label=template.get('lexical_anchor') or template.get('lemma') or template.get('surface')
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
