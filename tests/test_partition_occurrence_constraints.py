"""Finite source choices must preserve reachable discontinuous partitions."""
from types import SimpleNamespace
from ah.formalizer.partition_domain import PartitionDomain,ContentRequired
from ah.formalizer import structural_tasks


def setup(monkeypatch,steps,required):
    tokens=[SimpleNamespace(token_id=str(i),span='word',start=i,end=i+1) for i in range(5)]
    state=SimpleNamespace(syntax_trace=[],diag=lambda *a:None)
    region=SimpleNamespace(region_id='test',source_range=(0,5))
    domain=PartitionDomain(state,None,None,region,tokens,{},'CONTENT',{})
    domain.constraints=[ContentRequired(tuple(required),'test')]
    offered=[]
    def choose(*args,empty=None):
        options=list(args[-2]);offered.append((args[-3],options,empty))
        if not steps:return (empty,{}) if empty is not None else None
        wanted=steps.pop(0)
        found=next((v for v in options if v['candidate_id']==wanted),None)
        assert found is not None,(wanted,options)
        return found,{}
    monkeypatch.setattr(structural_tasks,'choose',choose)
    return domain,tokens,offered


def test_forbidden_occurrence_is_absent_from_all_marker_choices_but_not_its_homograph(monkeypatch):
    domain,tokens,offered=setup(monkeypatch,['start:0','end:0','2','2'],['1'])
    selected=domain.span(tokens,'marker','Select marker.',marker=True)
    assert [t.token_id for t in selected[0]]==['0','2']
    for slot,options,empty in offered:
        assert not any(v['candidate_id'] in {'1','start:1','end:1'} for v in options)
    # A separate relation keeps its own domain despite identical source spellings.
    fresh=PartitionDomain(domain.state,None,None,domain.region,tokens,{},'NOT',{})
    assert not fresh.required and domain.required=={'1'}


def test_required_words_can_be_collected_in_separate_pieces_before_completion(monkeypatch):
    domain,tokens,offered=setup(monkeypatch,['start:0','end:0','4','4'],['0','4'])
    selected=domain.span(tokens,'content','Select content.')
    assert [t.token_id for t in selected[0]]==['0','4']
    continues=[empty for slot,options,empty in offered if slot.endswith('_continue')]
    assert continues[0] is None and continues[-1]['candidate_id']=='DONE'


def test_partial_piece_must_not_prematurely_require_a_continuous_remainder(monkeypatch):
    domain,tokens,offered=setup(monkeypatch,['start:2','end:2','0','0'],['0','4'])
    selected=domain.span(tokens,'operand','Select operand.',remaining_parts=1,remaining_contiguous=True)
    assert [t.token_id for t in selected[0]]==['0','2']
    # At {2}, required {0,4} spans two remainder runs. Adding {0} makes {3,4}
    # a valid continuous second operand; rejecting {2} would lose this solution.
    continues=[empty for slot,options,empty in offered if slot.endswith('_continue')]
    assert continues[0] is None and continues[-1]['candidate_id']=='DONE'
