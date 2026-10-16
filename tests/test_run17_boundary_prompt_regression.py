"""Keep the measured boundary prompts small; show split previews in the GUI."""
import json
from pathlib import Path

import pytest

from test_structural_relation_tasks import run,relation,unary
from test_formalization_readable import sample
from ah.gui.formalization_inspection import Inspection
from ah.gui.formalization_readable import ReadableInspection

RECORDED=json.loads((Path(__file__).parent/'fixtures'/'run16_query_boundary_prompts.json').read_text())


@pytest.mark.parametrize('recorded',RECORDED,ids=lambda row:row['case_id'])
def test_query_boundaries_use_the_recorded_pre_regression_prompts(tmp_path,monkeypatch,recorded):
    result,script=run(tmp_path,monkeypatch,recorded['text'],
        unary('QUERY','Верно','что')+relation('LEXICAL'),kind='QUERY')
    for expected in recorded['prompts']:
        prompt=next(str(p) for slot,p in script.calls if slot==expected['slot'])
        assert prompt==expected['prompt']
    assert not result['assertions']['ah']
    assert result['generation']['observed_candidate_patterns'][0]['predicate']=='ENTER'
    assert result['diagnostics']['codes']==['SPEECH_ACT_QUERY']


def test_gui_boundary_preview_uses_recorded_refs_even_when_the_model_label_is_short():
    reader=ReadableInspection(Inspection(sample()))
    text=reader.task_choice({'boundary_end_ref':'student','selected_refs':['student'],
                            'remainder_refs':['read'],'label':'End after «студент» @14; selected words «студент»'})
    assert 'Слова связи: «студент»' in text
    assert 'останется: «читает»' in text
    assert 'remainder_refs' not in text
    empty=reader.task_choice({'boundary_end_ref':'read','selected_refs':['student','read'],
                             'remainder_refs':[]})
    assert 'останется: «»' in empty
