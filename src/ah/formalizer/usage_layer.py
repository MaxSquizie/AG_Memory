"""Typed SOM links. Access is a transitive least fixed point from proof-backed roots."""
from dataclasses import dataclass
from .canonical_ledger import digest

ALLOWED_KINDS={'ATTITUDE','OPERATOR'}

@dataclass
class UsageLink:
    link_id: str
    source_ref: str
    target_ref: str
    kind: str
    status: str='LIVE'
    position: str=''
    source_tag: tuple | None=None
    attitude: str | None=None

class UsageLayer:
    def __init__(self,nodes):
        self.nodes=nodes; self.links={}; self.live=set()

    def add_link(self,source_ref,target_ref,*,kind='OPERATOR',position='0',source_tag=None,attitude=None):
        if kind not in ALLOWED_KINDS or any(self.nodes[n]['kind'] not in {'N','G'} for n in (source_ref,target_ref)):
            raise ValueError('USAGE_LINK_INVALID')
        if kind=='ATTITUDE' and (source_tag is None or attitude not in {'QUOTED','EMBEDDED','HYPOTHETICAL','UNKNOWN'}):
            raise ValueError('ATTITUDE_LINK_INVALID')
        key=[target_ref,source_ref,position,kind]
        if kind=='ATTITUDE': key.append(source_tag)
        rid=digest(key)
        self.links.setdefault(rid,UsageLink(rid,source_ref,target_ref,kind,position=position,source_tag=source_tag,attitude=attitude))
        return self.links[rid]

    def set_live(self,node_id,is_live):
        if is_live: self.live.add(node_id)
        else: self.live.discard(node_id)

    def accessible(self):
        acc=set(self.live)
        while True:
            new={l.target_ref for l in self.links.values() if l.status=='LIVE' and l.source_ref in acc}
            if new<=acc: return acc
            acc.update(new)

    def s_accessible(self,node_id): return node_id in self.accessible()

    def retract_link(self,link_id):
        l=self.links[link_id]
        if l.kind=='OPERATOR': raise ValueError('RETRACT_OPERATOR_LINK_FORBIDDEN')
        l.status='SUPERSEDED'

    def supersede(self,node_id):
        before=self.accessible(); self.set_live(node_id,False)
        return before-self.accessible()  # canonical OPERATOR links remain LIVE
