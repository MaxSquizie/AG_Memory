"""Finite source-window provider accounting, independent of transport and WAL."""
from .canonical_ledger import digest


class WindowTokens:
    def __init__(self, keys, limit, base_params):
        self.limits={key:limit for key in keys}
        self.used={key:0 for key in keys}
        self.key=None
        self.params=digest({'provider_params':base_params,'source_window_tokens':self.limits})

    def enter(self,key):
        if key not in self.limits: raise ValueError('PROBE_SCOPE_UNKNOWN')
        self.key=key

    def available(self,cost):
        return self.key is not None and self.used[self.key]+cost<=self.limits[self.key]

    def charge(self,cost):
        self.used[self.key]+=cost

    def reset(self):
        self.used={key:0 for key in self.limits}; self.key=None

    def params_hash(self):
        return digest([self.params,self.key])
