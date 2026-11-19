"""The text grammar's bounded choice on the TypeSafe System One wire."""
from collections.abc import Mapping
from dataclasses import dataclass
import json


DEFAULT_JEV_MODEL = 'jev-latest'
QUESTION_ID = 'grammar'
CONTROL_CHOICES = {'0': 'None of the proposed answers fits.', '?': 'The sentence leaves the choice unclear.'}
MAX_WORD_CHOICES = 255 - len(CONTROL_CHOICES)


@dataclass(frozen=True)
class Probe:
    question: str
    options: tuple[str, ...]
    context: str

    def jev_request(self, model: str = DEFAULT_JEV_MODEL) -> dict:
        if not 1 <= len(self.options) <= MAX_WORD_CHOICES:
            raise ValueError('Jev Choice accepts at most 255 criteria including control choices')
        criteria = dict.fromkeys(self.options)
        if len(criteria) != len(self.options) or criteria.keys() & CONTROL_CHOICES.keys():
            raise ValueError('choice labels must be distinct from each other and from control choices')
        criteria.update(CONTROL_CHOICES)
        return {'model': model, 'state': self.context, 'questions': {
            QUESTION_ID: {'type': 'choice', 'instructions': self.question, 'criteria': criteria},
        }}

    def prompt(self, model: str = DEFAULT_JEV_MODEL) -> str:
        return json.dumps(self.jev_request(model), ensure_ascii=False)

    def response_choice(self, response: Mapping) -> str | None:
        answers = response.get('answers')
        answer = answers.get(QUESTION_ID) if isinstance(answers, Mapping) else None
        if not isinstance(answer, Mapping) or answer.get('type') != 'choice':
            return None
        choice = answer.get('choice')
        if isinstance(choice, str) and (choice in self.options or choice in CONTROL_CHOICES):
            return choice
        return None
