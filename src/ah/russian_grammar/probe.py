"""Readable grammar probes and their System One adapter."""
from collections.abc import Mapping
from dataclasses import dataclass, field


DEFAULT_JEV_MODEL = 'jev-latest'
QUESTION_ID = 'grammar'
CONTROL_CHOICES = {'0': 'None of the proposed answers fits.', '?': 'The sentence leaves the choice unclear.'}
OPTIONS_HEADER = '\nAnswer options:\n'
CONTROL_LINES = tuple(f'- {key} — {meaning}' for key, meaning in CONTROL_CHOICES.items())
MAX_WORD_CHOICES = 255 - len(CONTROL_CHOICES)


@dataclass(frozen=True)
class FocusChoice:
    modifier: int
    members: tuple[int, ...]


@dataclass(frozen=True)
class Probe:
    question: str
    options: tuple[str, ...]
    context: str
    focus_choices: tuple[FocusChoice, ...] = field(default=(), compare=False, repr=False)

    def jev_request(self, model: str = DEFAULT_JEV_MODEL) -> dict:
        if not 1 <= len(self.options) <= MAX_WORD_CHOICES:
            raise ValueError('Jev Choice accepts at most 255 criteria including control choices')
        criteria = dict.fromkeys(self.options)
        criteria.update(CONTROL_CHOICES)
        return {'model': model, 'state': self.context, 'questions': {
            QUESTION_ID: {'type': 'choice', 'instructions': self.question, 'criteria': criteria},
        }}

    def __post_init__(self):
        if not self.question.strip() or '\n' in self.question or '\r' in self.question:
            raise ValueError('expected a single-line question')
        if not self.options or any(not word.strip() or '\n' in word or '\r' in word for word in self.options):
            raise ValueError('expected one or more single-line answer options')
        labels = {' '.join(word.split()).casefold() for word in self.options}
        if len(labels) != len(self.options) or labels & CONTROL_CHOICES.keys():
            raise ValueError('answer options must be distinct from each other and from control choices')

    def prompt(self) -> str:
        lines = [f'- {label}' for label in self.options]
        return self.context + '\n\n' + self.question + OPTIONS_HEADER + '\n'.join([*lines, *CONTROL_LINES])

    @classmethod
    def from_prompt(cls, text: str) -> 'Probe':
        # Reading from the end keeps even a literal options header inside the sentence.
        newline = '\r\n' if text.rstrip('\r\n').endswith('\r\n' + CONTROL_LINES[-1]) else '\n'
        body, header, listing = text.removesuffix(newline).rpartition(OPTIONS_HEADER.replace('\n', newline))
        context, separator, question = body.rpartition(newline * 2)
        if not header or not separator:
            raise ValueError('expected a sentence, question and answer list')
        lines = listing.split(newline)
        if tuple(lines[-len(CONTROL_LINES):]) != CONTROL_LINES:
            raise ValueError('missing control choices')
        choices = lines[:-len(CONTROL_LINES)]
        if any(not line.startswith('- ') for line in choices):
            raise ValueError('expected one bullet per answer option')
        return cls(question, tuple(line[2:] for line in choices), context)

    def response_choice(self, response: Mapping) -> str | None:
        answers = response.get('answers')
        answer = answers.get(QUESTION_ID) if isinstance(answers, Mapping) else None
        if not isinstance(answer, Mapping) or answer.get('type') != 'choice':
            return None
        choice = answer.get('choice')
        if isinstance(choice, str) and (choice in self.options or choice in CONTROL_CHOICES):
            return choice
        return None
