from __future__ import annotations

from ah.russian_grammar.probe import CONTROL_CHOICES, Probe


class PendingChoice(Exception):
    def __init__(self, probe: Probe):
        super().__init__(probe.question)
        self.probe = probe


class GrammarChat:
    def __init__(self):
        self.reset()

    def reset(self):
        self.source = ''
        self.pending: Probe | None = None
        self.answers: list[tuple[Probe, str]] = []

    def send(self, text, submit):
        if self.pending is None:
            self.source = text
        else:
            choices = {word.casefold(): word for word in (*self.pending.options, *CONTROL_CHOICES)}
            answer = choices.get(' '.join(text.split()).casefold())
            if answer is None:
                return 'Введите один из указанных вариантов.\n\n' + self.pending.prompt()
            self.answers.append((self.pending, answer))

        answers = iter(self.answers)

        def choose(probe):
            prior = next(answers, None)
            if prior is None:
                raise PendingChoice(probe)
            if prior[0] != probe:
                raise ValueError('Набор проб изменился. Отправьте исходную фразу заново.')
            return prior[1]

        try:
            reply = submit(self.source, choose)
        except PendingChoice as choice:
            self.pending = choice.probe
            return choice.probe.prompt()
        except Exception:
            self.reset()
            raise
        self.reset()
        return reply.text
