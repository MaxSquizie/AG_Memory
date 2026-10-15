"""Model text with separate, durable closed-choice addressing metadata.

It is a string at every backend/HTTP boundary. Prefixing task instructions
retains metadata, but JSON serializes only the text shown to the model.
"""
from copy import deepcopy


class SelectionPrompt(str):
    def __new__(cls, text, audit):
        value = super().__new__(cls, text)
        value.selection_audit = deepcopy(audit)
        return value

    def __add__(self, other):
        return SelectionPrompt(str(self) + other, self.selection_audit)

    def __radd__(self, other):
        return SelectionPrompt(other + str(self), self.selection_audit)

    def __reduce__(self):
        return type(self), (str(self), self.selection_audit)


def record_prompt(decision, prompt):
    decision.last_prompt = str(prompt)
    audit = getattr(prompt, 'selection_audit', None)
    if audit is not None:
        decision.history.append({'kind': 'SELECTION_LABEL_MAP', **deepcopy(audit)})
