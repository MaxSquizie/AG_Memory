"""Readable grammar probes and their System One adapter."""
from collections.abc import Mapping
from dataclasses import dataclass, field


DEFAULT_JEV_MODEL = 'jev-latest'
QUESTION_ID = 'grammar'
CONTROL_CHOICES = {'0': 'None of the proposed answers fits.', '?': 'The sentence leaves the choice unclear.'}
OPTIONS_HEADER = '\nAnswer options:\n'
RUSSIAN_HEADER = '\nВарианты ответа:\n'
RUSSIAN_CONTROLS = {'0': 'Ни один вариант не подходит.', '?': 'По тексту нельзя выбрать однозначно.'}
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
    _russian_controls: bool | None = field(default=None, compare=False, repr=False, kw_only=True)

    def _format(self):
        russian = self._russian_controls
        if russian is None:
            first = self.question.lstrip()[0].lower()
            russian = 'а' <= first <= 'я' or first == 'ё'
        if russian:
            return RUSSIAN_HEADER, RUSSIAN_CONTROLS
        return OPTIONS_HEADER, CONTROL_CHOICES

    def jev_request(self, model: str = DEFAULT_JEV_MODEL) -> dict:
        if not 1 <= len(self.options) <= MAX_WORD_CHOICES:
            raise ValueError('Jev Choice accepts at most 255 criteria including control choices')
        criteria = dict.fromkeys(self.options)
        _, controls = self._format()
        criteria.update(controls)
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
        header, controls = self._format()
        lines = [f'- {label}' for label in self.options]
        lines.extend(f'- {key} — {description}' for key, description in controls.items())
        return self.context + '\n\n' + self.question + header + '\n'.join(lines)

    @classmethod
    def from_prompt(cls, text: str) -> 'Probe':
        # Reading from the end keeps even a literal options header inside the sentence.
        stripped = text.rstrip('\r\n')
        header_text, controls = ((RUSSIAN_HEADER, RUSSIAN_CONTROLS) if stripped.endswith(RUSSIAN_CONTROLS['?'])
                                 else (OPTIONS_HEADER, CONTROL_CHOICES))
        control_lines = tuple(f'- {key} — {meaning}' for key, meaning in controls.items())
        newline = '\r\n' if stripped.endswith('\r\n' + control_lines[-1]) else '\n'
        body, header, listing = text.removesuffix(newline).rpartition(header_text.replace('\n', newline))
        context, separator, question = body.rpartition(newline * 2)
        if not header or not separator:
            raise ValueError('expected a sentence, question and answer list')
        lines = listing.split(newline)
        if tuple(lines[-len(control_lines):]) != control_lines:
            raise ValueError('missing control choices')
        choices = lines[:-len(control_lines)]
        if any(not line.startswith('- ') for line in choices):
            raise ValueError('expected one bullet per answer option')
        return cls(question, tuple(line[2:] for line in choices), context,
                   _russian_controls=controls is RUSSIAN_CONTROLS)

    def response_choice(self, response: Mapping) -> str | None:
        answers = response.get('answers')
        answer = answers.get(QUESTION_ID) if isinstance(answers, Mapping) else None
        if not isinstance(answer, Mapping) or answer.get('type') != 'choice':
            return None
        choice = answer.get('choice')
        if isinstance(choice, str) and (choice in self.options or choice in CONTROL_CHOICES):
            return choice
        return None
