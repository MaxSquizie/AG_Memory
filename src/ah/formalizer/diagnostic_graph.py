"""Bounded observer projection from receipt references, never a reasoner read."""
from copy import deepcopy


def capture(store,refs,limit=10000):
    nodes=store.ledger.data['nodes'];pending=list(refs);seen=set();result={}
    while pending and len(seen)<limit:
        ref=pending.pop()
        if not isinstance(ref,str) or ref in seen:continue
        seen.add(ref);node=nodes.get(ref)
        if node is None:continue
        result[ref]=deepcopy(node)
        values=[*node.get('operands',()),*node.get('actants',{}).values(),node.get('template_ref')]
        pending.extend(v for v in values if isinstance(v,str) and v not in seen)
    return {'receipt_refs':list(refs),'nodes':result,'truncated':bool(pending),
            'remaining_refs':sorted(set(v for v in pending if isinstance(v,str))),
            'semantics':'STRUCTURAL_DESCENDANTS_ARE_NOT_INDEPENDENT_FACTS'}


def configuration(config):
    """Small allowlist for review exports; never API keys or a full config."""
    if config is None:return {}
    llm=getattr(config,'llm',None)
    fields=('backend','lmstudio_model','ollama_model','temperature','max_new_tokens')
    return {'llm':{k:getattr(llm,k) for k in fields if hasattr(llm,k)},
            'structure_mode':getattr(getattr(config,'formalizer',None),'structure_mode',None)}
