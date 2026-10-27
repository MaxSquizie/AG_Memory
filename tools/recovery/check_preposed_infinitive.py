"""Controlled source-order contrast: an infinitive complement precedes its head."""
import re
from tempfile import TemporaryDirectory
from pathlib import Path
from pytest import MonkeyPatch
from test_structural_relation_tasks import run,relation,bounds,Script

original=Script.generate
checked_reservations=set()
def generate(self,prompt,**kwargs):
    slot=re.search(r'Decision slot: (\S+)',prompt).group(1)
    labels=dict(re.findall(r'^(\d+)\. (.*)$',prompt,re.M))
    if slot=='predicate_argument_role':
        word=re.search(r'What role does «([^»]+)»',prompt).group(1)
        if word in {'Иван','Петра'}:
            assert not any(label.startswith('core object:') for label in labels.values())
            checked_reservations.add('parent')
        if word=='книгу':
            assert any(label.startswith('core object:') for label in labels.values())
            assert not any(label.startswith('core subject:') for label in labels.values())
            checked_reservations.add('child')
        role={'Иван':'core subject:','Петра':'recipient or addressee','книгу':'core object:'}.get(word)
        if role:return next(n for n,label in labels.items() if label.startswith(role))
    if slot=='predicate_argument_reading':
        word=re.search(r'reading of «([^»]+)»',prompt).group(1)
        case={'Иван':'nominative','Петра':'accusative','книгу':'accusative'}.get(word)
        if case:return next(n for n,label in labels.items() if case in label)
    return original(self,prompt,**kwargs)

steps=relation('CONTENT')+bounds('structural_content','книгу','прочитать')+bounds('structural_parent','Иван','Петра')+[
    ('structural_owner','Content belongs to predicate «попросил»'),('structural_partition','PARTITION'),
    ('structural_content_role','OBJECT:HYPOTHETICAL')]+relation('LEXICAL')+[
    ('structural_control','Same RECIPIENT')]+relation('LEXICAL')
with TemporaryDirectory() as directory,MonkeyPatch.context() as patch:
    patch.setattr(Script,'generate',generate)
    result,script=run(Path(directory),patch,'Иван попросил Петра книгу прочитать.',steps)
assert result['runtime']['report']['applied'] and not result['diagnostics']['codes']
assert checked_reservations=={'parent','child'}
assert result['assertions']['ah']==[{'predicate':'OPEN:попросить','roles':{
    'AGENT':{'entity':'ivan'},'RECIPIENT':{'entity':'petr'},
    'CONTENT':{'predicate':'READ','roles':{'THEME':{'entity':'book'},'AGENT':{'entity':'petr'}}}}}]
print('PASS: preposed object retained; infinitive head selected; controlled subject is Petr; reading not asserted separately')
