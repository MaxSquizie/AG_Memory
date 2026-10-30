"""Addressed expansion windows, independent of semantic completion.

The synchronous composer demands children one at a time. At a window boundary
it unwinds without publishing a child result. The outer driver then permits
only that demanded continuation and replays the prefix through the dispatcher.
This is not a beam search: no candidate is removed or ranked here.
"""
from contextlib import contextmanager
from .canonical_ledger import digest
from .composition_dispatcher import canonical


class ExpansionRequired(Exception):
    def __init__(self, address, path):
        super().__init__(address)
        self.address = address
        self.path = path


class ExpansionWindows:
    def __init__(self, state, width=3):
        if not isinstance(width, int) or isinstance(width, bool) or width < 1:
            raise ValueError('COMPOSITION_EXPANSION_WIDTH_INVALID')
        self.state = state
        self.width = width
        self.path = []
        self.granted = set()
        self.frontier = {}

    @contextmanager
    def enter(self, key, inputs, feedback):
        item = (key, digest(canonical([inputs, feedback])))
        path = tuple(self.path + [item])
        address = digest(path)
        # A grant starts a fresh window at this exact occurrence and contract.
        base = 0
        for index in range(1, len(path) + 1):
            if digest(path[:index]) in self.granted:
                base = index - 1
        if len(self.path) - base >= self.width:
            self.frontier[address] = {'child_key': key, 'path': path,
                'inputs': canonical(inputs), 'feedback': canonical(feedback),
                'status': 'DEFERRED'}
            self.state.syntax_trace.append({'kind': 'COMPOSITION_EXPANSION_DEFERRED',
                'continuation_ref': address, 'child_key': key,
                'depth': len(self.path), 'window': self.width,
                'structure_complete': False, 'search_complete': False})
            raise ExpansionRequired(address, path)
        self.path.append(item)
        try:
            yield
            # Execution completed, not necessarily interpretation. The task's
            # own receipt retains any unresolved semantic obligations.
            self.frontier.pop(address, None)
        finally:
            self.path.pop()

    def demand(self, pending):
        if pending.address not in self.frontier or pending.address in self.granted:
            raise ValueError('COMPOSITION_EXPANSION_NO_PROGRESS')
        self.granted.add(pending.address)
        self.state.syntax_trace.append({'kind': 'COMPOSITION_EXPANSION_REQUESTED',
            'continuation_ref': pending.address,
            'child_key': self.frontier[pending.address]['child_key'],
            'reason': 'PARENT_REQUIRES_CHILD_RESULT', 'window': self.width})
        self.frontier[pending.address]['status'] = 'REQUESTED'
