"""Scope-aware static inventory; computed edges are syntactic, not reachability proofs."""
import ast,hashlib,json
from pathlib import Path
ROOT=Path.cwd(); OUT=ROOT/'docs/audits/probe_contract_20261028'
files=sorted((ROOT/'src').rglob('*.py'))
functions={};calls=[];modules={};errors=[]
def qualify(p):return '.'.join(p.relative_to(ROOT/'src').with_suffix('').parts)
def import_base(module,n):
    bits=module.split('.')[:-1]
    return '.'.join(bits[:len(bits)-n.level+1]+([n.module] if n.module else [])) if n.level else (n.module or '')
def bindings(body,module,prefix):
    found={}
    def walk(n):
        if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)):
            found[n.name]=prefix+'.'+n.name;return
        if isinstance(n,ast.ImportFrom):
            for a in n.names:found[a.asname or a.name]=import_base(module,n)+'.'+a.name
        elif isinstance(n,ast.Import):
            for a in n.names:found[a.asname or a.name.split('.')[0]]=a.name if a.asname else a.name.split('.')[0]
        for c in ast.iter_child_nodes(n):walk(c)
    for n in body:walk(n)
    return found
class Scan(ast.NodeVisitor):
    def __init__(self,p,tree,text):
        self.p,self.text=p,text;self.module=qualify(p);self.scopes=[bindings(tree.body,self.module,self.module)]
        self.owner=self.module;self.cls=None;self.function=None;self.scope_kinds=["module"]
    def resolve(self,n):
        if isinstance(n,ast.Name):
            for s,kind in reversed(list(zip(self.scopes,self.scope_kinds))):
                if kind=="class" and self.function is not None:continue
                if n.id in s:return s[n.id]
            return n.id
        if isinstance(n,ast.Attribute):
            if isinstance(n.value,ast.Name) and n.value.id=='self' and self.cls:return self.cls+'.'+n.attr
            return self.resolve(n.value)+'.'+n.attr
        return ast.unparse(n)
    def visit_ClassDef(self,n):self.enter(n,True)
    def visit_FunctionDef(self,n):self.enter(n,False)
    visit_AsyncFunctionDef=visit_FunctionDef
    def enter(self,n,isclass):
        old=(self.owner,self.cls,self.function)
        self.owner+='.'+n.name
        if isclass:self.cls=self.owner
        else:
            self.function=n
            functions[self.owner]={'file':str(self.p.relative_to(ROOT)),'line':n.lineno,'end':n.end_lineno,
                                  'arguments':ast.unparse(n.args),'returns':ast.unparse(n.returns) if n.returns else None}
        local=bindings(n.body,self.module,self.owner)
        if not isclass:
            for a in [*n.args.posonlyargs,*n.args.args,*n.args.kwonlyargs]:local.setdefault(a.arg,a.arg)
        self.scopes.append(local);self.scope_kinds.append("class" if isclass else "function")
        for c in n.body:self.visit(c)
        self.scopes.pop();self.scope_kinds.pop();self.owner,self.cls,self.function=old
    def visit_Call(self,n):
        name=ast.unparse(n.func);target=self.resolve(n.func)
        calls.append({'file':str(self.p.relative_to(ROOT)),'line':n.lineno,'owner':self.owner,
            'call':name,'target':target,'source':ast.unparse(n),
            'literal_arguments':[a.value for a in n.args if isinstance(a,ast.Constant) and isinstance(a.value,str)],
            'keywords':{k.arg:ast.unparse(k.value) for k in n.keywords if k.arg},
            'caller_extent':[self.function.lineno,self.function.end_lineno] if self.function else None})
        self.generic_visit(n)
for p in files:
    text=p.read_text()
    try:tree=ast.parse(text)
    except SyntaxError as e:errors.append([str(p),str(e)]);continue
    modules[qualify(p)]=str(p.relative_to(ROOT));Scan(p,tree,text).visit(tree)
# Explicit boundaries include wrappers and injected callback; spelling-based
# span is included only for the identified PartitionDomain receiver.
helpers={'ah.formalizer.'+s for s in (
 'component_probe._probe','component_nominal_questions.choose','structural_tasks.choose',
 'structural_tasks.choose_domain','structural_tasks.source_set','structural_tasks.span',
 'structural_tasks.extend_source_set','selection_exchange.exchange','component_probe_replay.execute')}
sites=[]
for c in calls:
    if not c['file'].startswith('src/ah/formalizer/'):continue
    terminal=c['call'].split('.')[-1]
    match=(c['target'] in helpers or c['call']=='domain.span' or terminal in {'select','propose_local','propose_lexical'}
           or c['call'] in {'self._probe','self.transport','self.backend.generate'})
    if not match:continue
    c=dict(c);c['id']='P'+str(len(sites)+1).zfill(3)
    raw=(ROOT/c['file']).read_text()
    node=next(n for n in ast.walk(ast.parse(raw)) if isinstance(n,ast.Call) and n.lineno==c['line'] and ast.unparse(n.func)==c['call'])
    c['source']=ast.get_source_segment(raw,node)
    c['classification']=('EXAMPLE' if c['file'].endswith('fake_selector.py') else
      'EMBEDDING_TRANSPORT' if c['file'].endswith('lexical_embedding.py') else
      'INJECTED_CALLBACK' if c['call']=='self._probe' else
      'TRANSPORT_OR_WRAPPER' if terminal in {'select','propose_local','propose_lexical','exchange','execute','transport','generate'} else 'SEMANTIC_CALL')
    if c['file'].endswith('composition_morphology.py'):c['classification']='LOCAL_COMPUTE_WRAPPER'
    if c['file'].endswith('partition_sequences.py') and c['call']=='select':c['classification']='PARTITION_BUILDER_CALLBACK'
    if c['file'].endswith('component_refinement.py') and c['call']=='select':c['classification']='REFINEMENT_WRAPPER'
    c['review']='STATIC_SOURCE_REVIEW; see family review and closure ledger'
    sites.append(c)
# Incoming syntactically resolved callers for each enclosing function.
for c in sites:
    c['direct_callers']=[{'file':r['file'],'line':r['line'],'owner':r['owner'],'call':r['call']}
                         for r in calls if r['target']==c['owner']]
    c['dynamic_boundary']='NOT_INFERRED_FROM_ABSENCE_OF_STATIC_CALLERS' if not c['direct_callers'] else 'STATIC_EDGE_NOT_RUNTIME_PROOF'
old=json.loads((OUT/'inventory.json').read_text())
oldkeys={(c['file'],c['line']) for c in old['callsites']};newkeys={(c['file'],c['line']) for c in sites}
result={'scope':'All src AST parsed; formalizer semantic/transport/callback call boundaries inventoried',
 'python_files_parsed':len(files),'formalizer_files':len([p for p in files if '/formalizer/' in str(p)]),
 'parse_errors':errors,'sites':sites,'added_vs_v1':[c['id'] for c in sites if (c['file'],c['line']) not in oldkeys],
 'missing_v1':sorted(oldkeys-newkeys),'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files},
 'limits':['Lexical name resolution is conservative; no points-to proof for arbitrary callbacks or external plugins.',
           'Conditional imports/assignments may have multiple targets; reported direct edges do not prove runtime reachability.',
           'All finite static sites reviewed, not all unbounded executions or model replies.']}
(OUT/'inventory_v2.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n')
# Detailed exact source cards preserve runtime expressions, not invented final prompts.
lines=['# Реестр v2: все найденные границы вызова','',
 'Это статические карточки. source — код сборки запроса, не окончательный текст конкретного исполнения.',
 'Семантические выводы и непроверенные обязательства вынесены в FAMILY_REVIEW.md и CLOSURE.md.','']
for c in sites:
    lines += [f"## {c['id']} — {c['file']}:{c['line']}",'',f"Владелец: `{c['owner']}`. Класс: {c['classification']}. Разрешённое имя: `{c['target']}`.",
              '', 'Статические вызывающие: '+('; '.join(f"{r['file']}:{r['line']} ({r['owner']})" for r in c['direct_callers']) or 'не найдены; это не доказательство недостижимости')+'.',
              '', '```python',c['source'],'```','']
(OUT/'CALLSITE_CARDS.md').write_text('\n'.join(lines))
(OUT/'static_edges.json').write_text(json.dumps([c for c in calls if c['target'] in functions],ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'src_files':len(files),'sites':len(sites),'added':[(c['id'],c['file'],c['line'],c['call']) for c in sites if c['id'] in result['added_vs_v1']],
 'missing_v1':result['missing_v1'],'errors':errors},ensure_ascii=False,indent=2))
