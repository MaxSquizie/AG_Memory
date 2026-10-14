"""Packed capture domains for released grammar, shared by recursive children.

Terminals are whole source readings. Partial states are domain restrictions,
not partially asserted frames. The same DomainNetwork propagates syntax and
composition constraints; branching only closes the surviving capture slots.
"""
from .canonical_ledger import digest
from .composition_domains import DomainNetwork


class GrammarChart:
    def __init__(self):
        self.terminals={}
        self.items={}

    def feature(self,rule,capture,token,variant,evaluate,spend):
        from .morphology_domain import clean
        key=digest([rule['input_feature_pattern']['captures'][capture],token.token_id,
                    token.span,clean(variant) if variant else None])
        if key not in self.terminals:self.terminals[key]=evaluate()
        else:
            # A reused feature proof consumes the same logical search fuel;
            # cache warmth must not change admission at the budget boundary.
            for _ in range(self.terminals[key][1]):spend()
        return self.terminals[key][0]

    def close(self,state,release,rule,options,window,spend):
        from .syntax_rules import _plain_variant, _constraint, _possible_ast, evaluate_ast
        values={name:{digest([state.evidence[i].token_id,_plain_variant(v)]):(i,v)
                      for i,v in choices} for name,choices in options.items()}
        key='grammar-domain:'+digest([release.sha256 if release else None,rule,
            [t.token_id for t in state.evidence[slice(*window)]],{n:list(v) for n,v in values.items()}])
        graph=DomainNetwork(values)
        names=list(values)
        for name in names:
            guards=[c for c in rule['constraints'] if c['left']==c['right']==name]
            if guards:graph.restrict(name,[cid for cid,value in values[name].items()
                if all(_constraint(c,{name:value}) is True for c in guards)],'GRAMMAR_SELF_CONSTRAINT')
        for index,left in enumerate(names):
            for right in names[index+1:]:
                constraints=[c for c in rule['constraints'] if {c['left'],c['right']}<={left,right}]
                def compatible(a,b,left=left,right=right,constraints=constraints):
                    if a[0]==b[0] and (rule['input_feature_pattern'].get('distinct',True) or a[1]!=b[1]):return False
                    return all(_constraint(c,{left:a,right:b}) is True for c in constraints)
                graph.connect(left,right,compatible,'GRAMMAR_CAPTURE_COHERENCE')
        row={'kind':'GRAMMAR_DOMAIN','event':'DOMAIN','stage':'T2','domain_ref':key,'rule_id':rule['rule_id'],
             'owned_token_refs':[t.token_id for t in state.evidence[slice(*window)]],
             'captures':{n:{cid:{'token_ref':state.evidence[i].token_id,'reading':_plain_variant(v)}
                 for cid,(i,v) in choices.items()} for n,choices in values.items()},'states':{},'edges':[]}
        state.syntax_trace.append(row)
        # Keep the live initial domain addressable for parent/child projections.
        self.items[key]=graph
        where=rule['input_feature_pattern'].get('where')
        def walk(network,parent=None,selection=None):
            spend()
            consistent=network.propagate(spend)
            sid='grammar-state:'+digest({n:list(v) for n,v in network.domains.items()})
            if parent:row['edges'].append({'from':parent,'to':sid,'selection':selection})
            if sid in row['states']:return
            record={'constraint_state':network.snapshot(),'status':'PARTIAL'}
            row['states'][sid]=record
            domains={n:list(v.values()) for n,v in network.domains.items()}
            if not consistent or where and True not in _possible_ast(where,domains,state,release,window,spend):
                record['status']='REJECTED';return
            open_slots=[n for n,v in network.domains.items() if len(v)>1]
            if not open_slots:
                assignment={n:next(iter(v.values())) for n,v in network.domains.items()}
                truth=evaluate_ast(where,assignment,state,release,window,spend) if where else True
                if truth is True and len({i for i,v in assignment.values()})>=rule['min_evidence']:
                    record['status']='COMPLETE';yield assignment
                else:record['status']='REJECTED'
                return
            name=min(open_slots,key=lambda n:(len(network.domains[n]),n))
            for cid in network.domains[name]:
                child=network.copy();child.restrict(name,[cid],'GRAMMAR_CAPTURE_BINDING')
                yield from walk(child,sid,{'capture':name,'reading_ref':cid})
        yield from walk(graph.copy())


def chart(state):
    if not hasattr(state,'_grammar_chart'):state._grammar_chart=GrammarChart()
    return state._grammar_chart
