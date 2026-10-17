"""Naming receives selected source slots, never a private lexical trigger."""
import pytest
from ah.formalizer.naming_probe import recognize_naming,naming_probe,run_naming,NamingProtocolError


class Selector:
    def __init__(self,reply):self.reply=reply;self.prompts=[]
    def select(self,prompt):self.prompts.append(prompt);return self.reply


@pytest.mark.parametrize('text,referent,value',[
    ('Меня зовут Илья.',(0,4),(11,15)),
    ('Я — Илья.',(0,1),(4,8)),
    ('Его прозвали Ветер.',(0,3),(13,18)),
])
def test_selected_slots_are_self_contained(text,referent,value):
    reading=recognize_naming(text,referent_range=referent,value_ranges=[value])[0]
    selector=Selector('{"decision":"NAME_VALUE","value":"'+reading.values[0]+'"}')
    result=naming_probe(selector,reading,('supplied source evidence',))
    assert result.name_value==text[slice(*value)]
    assert text in selector.prompts[0] and 'supplied source evidence' in selector.prompts[0]


def test_missing_structure_cannot_be_guessed_from_words():
    with pytest.raises(NamingProtocolError,match='SELECTED_STRUCTURE'):
        run_naming('Меня зовут Илья.',Selector(''))


@pytest.mark.parametrize('reply,outcome',[
    ('{"decision":"OTHER_PREDICATION"}','OTHER_PREDICATION'),
    ('{"decision":"UNCLEAR"}','UNCLEAR'),
    ('```json\n{"decision":"NAME_VALUE","value":"Илья"}\n```','NAME_VALUE'),
])
def test_reply_protocol(reply,outcome):
    r=recognize_naming('Я — Илья.',referent_range=(0,1),value_ranges=[(4,8)])[0]
    assert naming_probe(Selector(reply),r).outcome==outcome


def test_invented_value_rejected():
    r=recognize_naming('Я — Илья.',referent_range=(0,1),value_ranges=[(4,8)])[0]
    with pytest.raises(NamingProtocolError):naming_probe(Selector('{"decision":"NAME_VALUE","value":"Пётр"}'),r)
