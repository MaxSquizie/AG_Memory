"""Static navigation inventory; does not certify dynamic reachability or coverage."""
import ast
import json
import hashlib
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
TARGETS={'morphology_domain','nominal_readings','partial_readings','reading_decisions',
         'component_probe','component_probe_replay','composition_dispatcher','dispatch_evidence',
         'producer_reads','validation_graph','rx_cache','selection_domains','structural_tasks'}


def inventory():
    calls=[];cache_candidates=[];source_hash=hashlib.sha256()
    for path in sorted((ROOT/'src/ah/formalizer').rglob('*.py')):
        source=path.read_text();tree=ast.parse(source);relative=str(path.relative_to(ROOT))
        source_hash.update(relative.encode()+b'\0'+source.encode()+b'\0')
        aliases={}
        for node in ast.walk(tree):
            if isinstance(node,ast.ImportFrom) and node.module and node.module.split('.')[-1] in TARGETS:
                for alias in node.names:aliases[alias.asname or alias.name]=(node.module,alias.name)
        for node in ast.walk(tree):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in aliases:
                module,name=aliases[node.func.id]
                calls.append(dict(file=relative,line=node.lineno,module=module,symbol=name))
        if any(word in source.lower() for word in ('cache','memo')):
            cache_candidates.append(relative)
    return dict(base_commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        source_digest=source_hash.hexdigest(),source_scope='sorted src/ah/formalizer/**/*.py path and UTF-8 contents',
        method='AST import-alias call candidates; lexical cache/memo candidates',
        limitations=['Function-local aliases may shadow each other; these are navigation candidates.',
                     'Attribute calls, injected callbacks, dynamic imports and indirect calls require separate review.',
                     'Presence does not prove reachability; absence does not prove no dependency.'],
        calls=calls,cache_candidates=cache_candidates)


if __name__=='__main__':print(json.dumps(inventory(),ensure_ascii=False,indent=2))
