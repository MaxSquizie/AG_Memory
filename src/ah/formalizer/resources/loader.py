"""Load a reviewed, content-addressed resource release with dependency closure."""
from __future__ import annotations
import json
from pathlib import Path
from ..canonical_ledger import digest

class ResourceMissing(ValueError): pass

class ResourceRelease:
    REQUIRED={'R-S','R-V','TemplateMap','RoleRegistry','OpenTemplatePolicy','ScopeLexicon','AttitudeMap','ProposalPolicy','IncompatibilityRules','PredicateSchema','R-X3','DeclaredReads','TemporalRules','SyntaxRules','CandidateSchema'}
    def __init__(self,manifest,*,require_review=True,trusted_reviews=None):
        # Canonical map order must agree with the signed hash; caller-owned
        # dictionaries cannot mutate the loaded snapshot after construction.
        try: manifest=json.loads(json.dumps(manifest,ensure_ascii=False,sort_keys=True,allow_nan=False))
        except (ValueError,TypeError) as exc: raise ResourceMissing('RESOURCE_MISSING: invalid JSON values') from exc
        self.manifest=manifest
        signed={k:manifest[k] for k in ('kind','version','schema_version','entries','dependency_versions') if k in manifest}
        if set(signed)!={'kind','version','schema_version','entries','dependency_versions'}:
            raise ResourceMissing('RESOURCE_MISSING: incomplete release manifest')
        if (not isinstance(manifest['version'],str) or not manifest['version']
                or not isinstance(manifest['entries'],list) or not isinstance(manifest['dependency_versions'],dict)
                or not set(manifest)<={'kind','version','schema_version','entries','dependency_versions','coverage_report','signed_review_id'}):
            raise ResourceMissing('RESOURCE_MISSING: invalid release container')
        self.content_sha256=digest(signed)
        if 'coverage_report' in manifest: signed['coverage_report']=manifest['coverage_report']
        self.sha256=digest(signed)
        review=manifest.get('signed_review_id') or {}
        if require_review and (review.get('reviewed_sha256')!=self.sha256 or not all(review.get(k) for k in ('reviewer','signature','timestamp')) or not manifest.get('coverage_report')):
            raise ResourceMissing('RESOURCE_MISSING: release has no matching review/coverage')
        if manifest['schema_version']!='v7' or manifest['kind']!='FORMALIZER_RESOURCE_RELEASE':
            raise ResourceMissing('RESOURCE_MISSING: unsupported release schema/kind')
        coverage=manifest.get('coverage_report',{})
        if require_review and (not {'corpus_id','corpus_sha256','units_by_kind','categories'}<=set(coverage) or len(str(coverage.get('corpus_sha256','')))!=64):
            raise ResourceMissing('RESOURCE_MISSING: invalid coverage report')
        if require_review:
            from .signatures import verify_review
            try:
                verify_review(review, trusted_reviews, self.sha256)
            except Exception as exc:
                raise ResourceMissing('RESOURCE_MISSING: review signature/trust validation failed') from exc
        self.resources={}
        for entry in manifest['entries']:
            if (not isinstance(entry,dict) or set(entry)!={'kind','version','schema_version','entries','dependency_versions'}
                    or not isinstance(entry['kind'],str) or not entry['kind'] or not isinstance(entry['version'],str) or not entry['version']
                    or not isinstance(entry['dependency_versions'],dict)
                    or any(not isinstance(k,str) or not k or not isinstance(v,str) or not v for k,v in entry['dependency_versions'].items())):
                raise ResourceMissing('RESOURCE_MISSING: incomplete resource')
            if not isinstance(entry['entries'],list) or not isinstance(entry['dependency_versions'],dict): raise ResourceMissing('invalid resource container')
            if entry['schema_version']!='v7': raise ResourceMissing('unsupported resource schema')
            kind=entry['kind']
            if kind in self.resources: raise ResourceMissing('duplicate resource kind:'+kind)
            self.resources[kind]=entry
        if self.REQUIRED-set(self.resources): raise ResourceMissing('RESOURCE_MISSING:'+','.join(sorted(self.REQUIRED-set(self.resources))))
        if 'coverage_report' in manifest:
            from .coverage import validate_coverage
            try: validate_coverage(manifest['coverage_report'],self.content_sha256,self.resources)
            except ValueError as exc: raise ResourceMissing('RESOURCE_MISSING: '+str(exc)) from exc
        from .schemas import validate_resources
        try: self.candidate_validators = validate_resources(self.resources)
        except ValueError as exc: raise ResourceMissing('RESOURCE_MISSING: '+str(exc)) from exc
        if set(manifest['dependency_versions'])!=set(self.resources):
            raise ResourceMissing('RESOURCE_MISSING: release must pin every resource version')
        active=set(); done=set()
        def visit(kind):
            if kind in active: raise ResourceMissing('RESOURCE_MISSING: cyclic dependency')
            if kind in done: return
            active.add(kind)
            for dep,version in self.resources[kind]['dependency_versions'].items():
                if dep not in self.resources or str(self.resources[dep]['version'])!=str(version):
                    raise ResourceMissing('RESOURCE_MISSING: unresolved dependency '+dep)
                visit(dep)
            active.remove(kind); done.add(kind)
        for kind in self.resources: visit(kind)
        for dep,version in manifest['dependency_versions'].items():
            if dep not in self.resources or str(self.resources[dep]['version'])!=str(version): raise ResourceMissing('RESOURCE_MISSING: release dependency '+dep)
        for key in ('OpenTemplatePolicy','ProposalPolicy'):
            if len(self.entries(key))!=1: raise ResourceMissing('exactly one '+key+' policy required')
        if 'CorefPolicy' in self.resources:
            if len(self.entries('CorefPolicy'))!=1 or self.entries('CorefPolicy')[0]['event_anaphora_rules']:
                raise ResourceMissing('RESOURCE_MISSING: one entity CorefPolicy required; event identity handlers are not registered')
        policy=self.entries('ProposalPolicy')[0]
        if any(type(policy.get(k)) is not int or policy[k]<=0 for k in ('max_nodes','max_edges','max_depth','max_source_tokens')): raise ResourceMissing('invalid proposal limits')
        if any(type(policy.get(k,default)) is not int or policy.get(k,default)<=0 for k,default in (('max_rule_steps',20000),('max_rule_matches',256))): raise ResourceMissing('invalid syntax search limits')
        if type(policy.get('verify_deterministic',False)) is not bool or type(self.entries('OpenTemplatePolicy')[0].get('allow')) is not bool: raise ResourceMissing('invalid proposal/open policy')
        senses=self.entries('R-S'); sense_ids={x['sense_id'] for x in senses}
        if len(sense_ids)!=len(senses): raise ResourceMissing('duplicate sense_id')
        if any(not x.get('lemma') or not x.get('POS') for x in senses): raise ResourceMissing('R-S requires lemma and POS')
        for sense in senses:
            pattern=sense.get('anchor_pattern')
            if pattern is not None and (not isinstance(pattern,list) or len(pattern)<2 or any(not isinstance(p,dict) or not p or not set(p)<={'lemma','POS'} or any(not isinstance(v,str) or not v for v in p.values()) for p in pattern)):
                raise ResourceMissing('invalid lexical-unit anchor pattern')
        roles={x['role_id'] for x in self.entries('RoleRegistry')}
        from ah.model.types import ActantRole
        if len(roles)!=len(self.entries('RoleRegistry')) or not roles<={r.value for r in ActantRole}:
            raise ResourceMissing('ADAPTER_NOT_COVERED: duplicate or unsupported role')
        if not {'EXPERIENCER','SURFACE_ARG'}<=roles: raise ResourceMissing('mandatory role missing')
        from ..syntax_rules import validate_rules
        self.syntax_rules = []
        try:
            from .rule_dsl import compile_rules
            for rule in self.resources['SyntaxRules']['entries']:
                self.syntax_rules.extend(compile_rules(rule['dsl'],roles,self.resources['SyntaxRules']['dependency_versions']).rules if 'dsl' in rule else [rule])
            validate_rules(self.syntax_rules, roles, self.resources['SyntaxRules']['dependency_versions'])
            for rule in self.syntax_rules:
                self.candidate_validators[rule['output_kind']].validate(rule['output'])
        except Exception as exc: raise ResourceMissing('RESOURCE_MISSING: invalid SyntaxRules: '+str(exc)) from exc
        self.syntax_sha256 = digest(self.syntax_rules)
        for v in self.entries('R-V'):
            if v.get('sense_id') not in sense_ids or v.get('state_class') not in {None,'STATE','EVENT'}: raise ResourceMissing('invalid R-V sense/class')
            if v.get('temporal_mode_hint') not in {None,'STATE','EVENT','PROCESS','TRANSITION'}: raise ResourceMissing('invalid frame temporal-mode hint')
            if any(r['role_id'] not in roles for r in v.get('roles',())): raise ResourceMissing('invalid R-V role')
            if len({r['role_id'] for r in v.get('roles',())})!=len(v.get('roles',())): raise ResourceMissing('duplicate R-V role')
            for r in v.get('roles',()):
                if not all(isinstance(r.get(k,[]),list) for k in ('allowed_cases','allowed_preps','argument_types')): raise ResourceMissing('invalid R-V role lists')
                cardinality=r.get('cardinality',{}); lo=cardinality.get('min',0); hi=cardinality.get('max',1)
                if type(lo) is not int or lo<0 or hi is not None and (type(hi) is not int or hi<lo): raise ResourceMissing('invalid role cardinality')
        for key in ('PredicateSchema','R-X3'):
            for x in self.entries(key):
                values=x.get('value_ids',()) if key=='PredicateSchema' else [x.get('sense_id')]
                if not x.get('lemma') or any(v not in sense_ids for v in values): raise ResourceMissing('invalid '+key+' sense')
                for ex in x.get('value_expansions',()):
                    if not ex.get('rule_id') or any(v not in sense_ids for v in ex['value_ids']): raise ResourceMissing('invalid ValueExpansionRule')
        for x in self.entries('DeclaredReads'):
            if not all(x.get(k) for k in ('read_id','lemma','snapshot_version')): raise ResourceMissing('invalid declared read')
        import re
        for x in self.entries('ScopeLexicon'):
            if x.get('operator') and x['operator'] not in {'NOT','AND','OR','XOR','IMPLIES','FORALL','EXISTS','POSSIBLE','NECESSARY','COUNTERFACTUAL','BEFORE','AFTER','DURING','ASSOCIATION','AT_LEAST_N','EXACTLY_N','AT_MOST_N'}: raise ResourceMissing('invalid scope operator')
            if x.get('pattern'): re.compile(x['pattern'])
        for x in self.entries('TemporalRules'):
            re.compile(x['pattern'])
            if x['kind'] not in {'POINT_CLOCK','DAY_INTERVAL','INTERVAL_CLOCK'} or x.get('interval_semantics','EXISTENTIAL') not in {'EXISTENTIAL','CONTINUOUS'}: raise ResourceMissing('invalid temporal rule')
        for x in self.entries('IncompatibilityRules'):
            if x.get('kind')!='ROLE_EXCLUSIVE' or not all(x.get(k) for k in ('rule_id','sense_id','role_id','key_roles')) or x['sense_id'] not in sense_ids or x['role_id'] not in roles: raise ResourceMissing('invalid incompatibility rule')
            if not set(x['key_roles'])<=roles: raise ResourceMissing('invalid incompatibility key roles')
        attitudes=set()
        for x in self.entries('AttitudeMap'):
            if not x.get('lemma') or x.get('argument_role') not in roles or x.get('attitude') not in {'QUOTED','EMBEDDED','HYPOTHETICAL','UNKNOWN'} or x.get('holder_role','SUBJECT') not in roles:
                raise ResourceMissing('invalid AttitudeMap')
            key=(x['lemma'],x['argument_role'])
            if key in attitudes: raise ResourceMissing('duplicate/ambiguous AttitudeMap key')
            attitudes.add(key)
        seen_mappings=set()
        for m in self.entries('TemplateMap'):
            if m['sense_id'] not in sense_ids or not m.get('template_ref') or not set(m.get('roles',()))<=roles: raise ResourceMissing('invalid TemplateMap')
            key=(m['sense_id'],tuple(sorted(m.get('roles',()))))
            if key in seen_mappings: raise ResourceMissing('conflicting TemplateMap key')
            seen_mappings.add(key)
        certificates=self.resources.get('DomainCertificate',{}).get('entries',())
        seen_domains=set()
        for c in certificates:
            if (not isinstance(c.get('domain_id'),str) or not c['domain_id'] or c['domain_id'] in seen_domains
                or not c.get('template_ref') or c.get('count_role') not in roles
                or not isinstance(c.get('known_roles'),dict) or not set(c['known_roles'])<=roles
                or c['count_role'] in c['known_roles'] or any(not isinstance(v,str) or not v for v in c['known_roles'].values())
                or not isinstance(c.get('completeness_evidence'),list) or not c['completeness_evidence']
                or any(not isinstance(v,str) or not v for v in c['completeness_evidence']) or not c.get('version')
                or 'request_window' not in c):
                raise ResourceMissing('invalid scoped DomainCertificate')
            window=c['request_window']
            if window is not None:
                from ah.model import TimeLiteral
                if not isinstance(window,list) or len(window)!=2: raise ResourceMissing('invalid domain window')
                try: TimeLiteral(tuple(window))
                except ValueError as exc: raise ResourceMissing('invalid domain window') from exc
            seen_domains.add(c['domain_id'])
        for c in self.resources.get('FormulaDomainCertificate',{}).get('entries',()):
            if c['domain_id'] in seen_domains: raise ResourceMissing('duplicate domain_id')
            if c['request_window'] is not None:
                from ah.model import TimeLiteral
                try: TimeLiteral(tuple(c['request_window']))
                except ValueError as exc: raise ResourceMissing('invalid formula domain window') from exc
            seen_domains.add(c['domain_id'])

    def entries(self,kind):
        return self.syntax_rules if kind == 'SyntaxRules' and hasattr(self, 'syntax_rules') else self.resources[kind]['entries']
    def version(self,kind): return str(self.resources[kind]['version'])

    def validate_store(self, store):
        """Validate every declared mapping against the actual AH before T0."""
        self.assert_integrity()
        from ah.model import RefKind
        for row in self.entries('TemplateMap'):
            uid = row['template_ref']
            if (not store.has_uid(uid) or store.kind_of(uid) is not RefKind.T
                    or {r.value for r in store.get_template(uid).roles} != set(row['roles'])):
                raise ResourceMissing('RESOURCE_MISSING: TemplateMap does not match actual AH T:' + uid)
        for row in self.resources.get('DomainCertificate', {}).get('entries', ()):
            uid=row['template_ref']
            if not store.has_uid(uid) or store.kind_of(uid) is not RefKind.T:
                raise ResourceMissing('RESOURCE_MISSING: certificate T missing:' + uid)
            if not set(row['known_roles'])|{row['count_role']} <= {r.value for r in store.get_template(uid).roles}:
                raise ResourceMissing('RESOURCE_MISSING: certificate roles mismatch')
            if any(not store.has_uid(m) or store.kind_of(m) is not RefKind.M for m in row['known_roles'].values()):
                raise ResourceMissing('RESOURCE_MISSING: certificate entity missing')

    def assert_integrity(self):
        signed={k:self.manifest[k] for k in ('kind','version','schema_version','entries','dependency_versions')}
        if 'coverage_report' in self.manifest: signed['coverage_report']=self.manifest['coverage_report']
        if digest(signed)!=self.sha256 or self.resources!={r['kind']:r for r in self.manifest['entries']} or digest(self.syntax_rules)!=self.syntax_sha256:
            raise ResourceMissing('INTEGRITY_ERROR: loaded resource snapshot changed')

    @classmethod
    def load(cls,path,**kwargs):
        try: raw=json.loads(Path(path).read_text(encoding='utf-8'))
        except (OSError,ValueError) as exc: raise ResourceMissing('RESOURCE_MISSING: '+str(path)) from exc
        try: return cls(raw,**kwargs)
        except (KeyError,TypeError,AttributeError) as exc: raise ResourceMissing('RESOURCE_MISSING: malformed release entry') from exc
