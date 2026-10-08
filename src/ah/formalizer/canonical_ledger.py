"""Canonical V7 records shared by batch, goal, retraction and query channels.

The dictionaries are persisted inside AH, not a second in-memory proof graph.
Visibility is a least fixed point over concrete support records. Node identity and
historical lifecycle events never act as terminal visibility flags.
"""
from __future__ import annotations

import hashlib
import json
from copy import deepcopy
from .temporal_license import TemporalRegion, normalize, covers, or_elimination_license, forall_inst_license


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def region(raw=None) -> TemporalRegion:
    if not raw:
        return TemporalRegion("UNDATED")
    if isinstance(raw, TemporalRegion):
        return raw
    return TemporalRegion(raw["kind"], point=raw.get("point"), lo=raw.get("lo"), hi=raw.get("hi"), points=frozenset(raw.get("points", ())))


def region_data(value: TemporalRegion) -> dict:
    return {"kind": value.kind, "point": value.point, "lo": value.lo, "hi": value.hi, "points": sorted(value.points)}


def simultaneous(a, b):
    a, b = normalize(region(a)), normalize(region(b))
    if a.kind == b.kind == "UNDATED":
        return True
    if "UNDATED" in (a.kind, b.kind):
        return False
    if a.kind == "POINT" and b.kind == "POINT":
        return a.point == b.point
    if a.kind == "CONTINUOUS" and b.kind == "CONTINUOUS":
        return all(x is not None for x in (a.lo,a.hi,b.lo,b.hi)) and max(a.lo,b.lo) <= min(a.hi,b.hi)
    if a.kind == "CONTINUOUS":
        return covers(a,b) is True
    if b.kind == "CONTINUOUS":
        return covers(b,a) is True
    return False


def incompatible(a,b,rules=()):
    if a.get('content_key')==b.get('content_key') and a.get('polarity',True)!=b.get('polarity',True):
        return 'ASSERTED_CONTRADICTION'
    if not a.get('polarity',True) or not b.get('polarity',True): return None
    pa,pb=a.get('proposition') or {},b.get('proposition') or {}
    for r in rules:
        if r['kind']!='ROLE_EXCLUSIVE' or pa.get('predicate')!=r['sense_id'] or pb.get('predicate')!=r['sense_id']: continue
        ra,rb=pa.get('actants',{}),pb.get('actants',{})
        if all(k in ra and k in rb and ra[k]==rb[k] for k in r['key_roles']) and r['role_id'] in ra and r['role_id'] in rb and ra[r['role_id']]!=rb[r['role_id']]: return r['rule_id']
    return None


class CanonicalLedger:
    def __init__(self, data=None):
        self.data = data if data is not None else {}
        for key in ("nodes", "supports", "bindings", "assertions", "usage_links", "observations", "candidates", "reports", "markers", "decisions", "goal_decisions", "goal_paths", "witnesses", "rx_cache", "open_template_links"):
            self.data.setdefault(key, {})
        self.data.setdefault("events", [])
        self.data.setdefault("closed_reports", {})

    def copy(self):
        return CanonicalLedger(deepcopy(self.data))

    def validate_audit(self):
        """Fail closed on damaged canonical audit; never repair append-only events."""
        def fail(message):
            raise ValueError('INTEGRITY_ERROR: '+message)
        identities=set(); order=None; created=set(); added=set(); retracted=set()
        seqs={}; transitions={}
        for event in self.data['events']:
            node,kind,tx=event['node_id'],event['type'],event['tx_ref']
            if node not in self.data['nodes']: fail('event refers to missing node')
            expected=[node,kind,tx]
            if kind in {'SUPPORT_ADDED','SUPPORT_RETRACTED'}:
                sid=event['support_id']; expected.append(sid)
                support=self.data['supports'].get(sid)
                if not support or support['conclusion_ref']!=node: fail('event support mismatch')
                if node not in created: fail('support precedes node creation')
                if kind=='SUPPORT_ADDED':
                    if sid in added: fail('duplicate support creation')
                    added.add(sid)
                else:
                    if sid not in added or sid in retracted: fail('invalid support retraction history')
                    retracted.add(sid)
            elif kind=='CREATED':
                if node in created: fail('duplicate node creation')
                created.add(node)
            elif kind in {'CASCADE_SUPERSEDED','REACCESSIBLE'}:
                if node not in created: fail('transition precedes creation')
                transitions[node]=kind
            else: fail('unknown lifecycle event')
            if event['identity']!=expected or tuple(expected) in identities:
                fail('event identity mismatch')
            identities.add(tuple(expected))
            key=(event['T'],event['seq'])
            if order is not None and key<=order: fail('event order mismatch')
            order=key
            if type(event['seq']) is not int or event['seq']!=seqs.get(tx,0): fail('event sequence gap')
            seqs[tx]=event['seq']+1
        if created!=set(self.data['nodes']): fail('missing node creation event')
        if added!=set(self.data['supports']): fail('missing support creation event')
        for sid,support in self.data['supports'].items():
            if (support['status']!='LIVE') != (sid in retracted): fail('support status/history mismatch')
        accessible=self.s_accessible()
        for node,kind in transitions.items():
            if (kind=='REACCESSIBLE') != (node in accessible): fail('node transition/current access mismatch')
        for entry in self.data['rx_cache'].values():
            if entry['support_record_id'] not in self.data['supports']:
                fail('RX entry without committed support')

    def paths(self):
        live = set()
        while True:
            new = set()
            for rid, s in self.data["supports"].items():
                if s["status"] != "LIVE" or any(self.data["bindings"].get(b,{}).get("status") != "LIVE" or any(p not in live for p in self.data["bindings"].get(b,{}).get("premise_support_refs",())) for b in s.get("binding_refs", ())):
                    continue
                if any(self.data["assertions"].get(a,{}).get("status") != "LIVE" or self.data["assertions"][a]["support_record_id"] not in live for a in s.get("temporal_assertion_refs", ())):
                    continue
                if s["kind"] == "ROOT" and s.get("ground_type") in {"O","C","W"}:
                    new.add(rid)
                elif s["kind"] == "DERIVED" and s.get("premise_support_refs") and all(p in live for p in s["premise_support_refs"]):
                    new.add(rid)
            if new <= live:
                return live
            live.update(new)

    def f_visible(self):
        paths = self.paths()
        return {s["conclusion_ref"] for rid,s in self.data["supports"].items() if rid in paths}

    def s_accessible(self):
        accessible = self.f_visible()
        while True:
            extra = {l["node_ref"] for l in self.data["usage_links"].values() if l["status"] == "LIVE" and l["parent_ref"] in accessible}
            if extra <= accessible:
                return accessible
            accessible.update(extra)

    def evidence_live(self, ref):
        kind = ref.get("kind", "COMMITTED")
        rid = ref["record_id"]
        if kind == "CANDIDATE":
            return self.data["candidates"].get(rid,{}).get("status") == "LIVE"
        a = self.data["assertions"].get(rid)
        if a is not None:
            return a["status"] == "LIVE" and a["support_record_id"] in self.paths()
        return rid in self.paths()  # undated committed evidence names a particular support

    def report_open(self, report):
        return report["report_id"] not in self.data["closed_reports"] and all(self.evidence_live(e) for e in report["evidence_refs"])

    def refresh(self, before, tx_ref, T, support_events=()):
        events = []
        effective=self.paths()
        for rid,s in self.data["supports"].items():
            if s["status"]=="LIVE" and rid not in effective:
                s["status"]="SUPERSEDED"
                events.append({"node_id":s["conclusion_ref"],"type":"SUPPORT_RETRACTED","support_id":rid})
        for node in sorted(set(self.data["nodes"]) - set(before.data["nodes"])):
            events.append({"node_id":node,"type":"CREATED"})
        events.extend(support_events)
        old, new = before.s_accessible(), self.s_accessible()
        for node in sorted(old - new):
            events.append({"node_id":node,"type":"CASCADE_SUPERSEDED"})
        for node in sorted((new-old) & set(before.data["nodes"])):
            events.append({"node_id":node,"type":"REACCESSIBLE"})
        created=[e for e in events if e['type']=='CREATED']
        added=[e for e in events if e['type']=='SUPPORT_ADDED']
        retracted=sorted((e for e in events if e['type']=='SUPPORT_RETRACTED'),key=lambda e:e['support_id'])
        transitions=sorted((e for e in events if e['type'] in {'CASCADE_SUPERSEDED','REACCESSIBLE'}),key=lambda e:e['node_id'])
        events=created+added+retracted+transitions
        known = {tuple(e["identity"]) for e in self.data["events"]}
        for seq, e in enumerate(events):
            ident = [e["node_id"],e["type"],tx_ref]
            if e["type"] in {"SUPPORT_ADDED","SUPPORT_RETRACTED"}:
                ident.append(e["support_id"])
            if tuple(ident) in known:
                continue
            e.update(identity=ident,tx_ref=tx_ref,T=T,seq=seq)
            self.data["events"].append(e)
            known.add(tuple(ident))
        for rid, r in self.data["reports"].items():
            if rid not in self.data["closed_reports"] and not all(self.evidence_live(e) for e in r["evidence_refs"]):
                statuses=[self.data['assertions'].get(e['record_id'],self.data['supports'].get(e['record_id'],self.data['candidates'].get(e['record_id'],{}))).get('status') for e in r['evidence_refs']]
                self.data["closed_reports"][rid] = {"report_id":rid,"closed_by":"SUPERSEDE" if 'SUPERSEDED' in statuses else "RETRACTION","tx_ref":tx_ref}
        paths=self.paths()
        for entry in self.data['rx_cache'].values():
            if entry['status']=='LIVE' and entry['support_record_id'] not in paths:
                entry['status']='STALE'

    def add_support(self, raw):
        raw = deepcopy(raw)
        raw.setdefault("status","LIVE")
        if raw["kind"] == "ROOT" and raw.get("ground_type") not in {"O","C","W"}:
            raise ValueError("INVALID_FACT_GROUND")
        if raw["kind"] == "DERIVED" and not raw.get("premise_support_refs"):
            raise ValueError("GOAL_NO_PREMISES")
        rid = raw["record_id"]
        existing = self.data["supports"].get(rid)
        if existing is not None and existing != raw:
            raise ValueError("INTEGRITY_ERROR: support identity changed")
        self.data["supports"].setdefault(rid, raw)

    def add_assertion(self, raw):
        raw = deepcopy(raw)
        raw.setdefault("status","LIVE")
        s = self.data["supports"].get(raw["support_record_id"])
        if s is None or s["conclusion_ref"] != raw["target_ref"]:
            raise ValueError("TIME_ASSERTION_SUPPORT_MISMATCH")
        source, support = raw["provenance"]["source"], raw["provenance"]["support"]
        if support.get('kind')!=s['kind']:
            raise ValueError('TIME_ASSERTION_PROVENANCE_INVALID')
        if source["kind"] == "GOAL_RUN":
            if support["kind"] != "DERIVED" or not source.get("goal_run_id") or source['goal_run_id']!=s.get('goal_run_id') or support.get("rule_id") != s.get("rule_id") or support.get("premise_support_refs") != s.get("premise_support_refs"):
                raise ValueError("TIME_ASSERTION_PROVENANCE_INVALID")
        elif source["kind"] == "OBSERVATION":
            if source.get("source_tag") != s.get("source_tag") or (support["kind"] == "DERIVED" and s.get("rule_id") != "AND_ELIMINATION"):
                raise ValueError("TIME_ASSERTION_PROVENANCE_INVALID")
        else:
            raise ValueError("TIME_ASSERTION_PROVENANCE_INVALID")
        r = region(raw["region"])
        if r.kind == "UNDATED":
            raise ValueError("UNDATED_ASSERTION_FORBIDDEN")
        if r.kind not in {"POINT","CONTINUOUS","EXISTENTIAL"} or (r.kind == "POINT" and r.point is None) or (r.lo is not None and r.hi is not None and r.lo > r.hi):
            raise ValueError("TIME_ASSERTION_REGION_INVALID")
        raw["region"]=region_data(r)
        witness=raw.get('witness_ref')
        if witness:
            origin=self.data['witnesses'].get(witness)
            if s['kind']=='ROOT':
                if self.data['nodes'][s['conclusion_ref']].get('function_id')!='AND': raise ValueError('WITNESS_ORIGIN_INVALID')
                expected={'root_support_id':s['record_id'],'region':raw['region']}
                if origin and origin!=expected: raise ValueError('WITNESS_IDENTITY_CONFLICT')
                self.data['witnesses'][witness]=expected
            else:
                premise_evidence=[a for a in self.data['assertions'].values() if a['support_record_id'] in s['premise_support_refs'] and a.get('witness_ref')==witness]
                if not origin or not premise_evidence or not any(digest(a['region'])==digest(raw['region']) for a in premise_evidence): raise ValueError('WITNESS_DERIVATION_INVALID')
        existing = self.data["assertions"].get(raw["assertion_id"])
        if existing is not None and existing != raw:
            raise ValueError("INTEGRITY_ERROR: assertion identity changed")
        self.data["assertions"].setdefault(raw["assertion_id"],raw)

    def retract(self, *, source_tag=None, assertion_id=None, binding_id=None,source_status='RETRACTED'):
        if source_status not in {'RETRACTED','SUPERSEDED'}: raise ValueError('INVALID_RETRACTION_STATUS')
        events=[]
        if source_tag is not None:
            tag = list(source_tag)
            for rid,s in sorted(self.data["supports"].items()):
                if s.get("source_tag") == tag and s["status"] == "LIVE":
                    s["status"] = "SUPERSEDED"
                    events.append({"node_id":s["conclusion_ref"],"type":"SUPPORT_RETRACTED","support_id":rid})
            for a in self.data["assertions"].values():
                if a["provenance"]["source"].get("source_tag") == tag and a['status']=='LIVE':
                    a["status"] = source_status
            for c in self.data["candidates"].values():
                if c.get("source_tag") == tag and c['status']=='LIVE':
                    c["status"] = source_status
            for l in self.data["usage_links"].values():
                if l["kind"] == "ATTITUDE" and l.get("source_tag") == tag:
                    l["status"] = "SUPERSEDED"
        if assertion_id is not None and self.data['assertions'][assertion_id]['status']=='LIVE':
            self.data["assertions"][assertion_id]["status"] = "RETRACTED"
        if binding_id is not None:
            self.data["bindings"][binding_id]["status"] = "INVALID"
        return events

    def supersede(self, source_tag):
        """Terminal old-version records; callers commit this with the replacement."""
        tag=list(source_tag)
        events=self.retract(source_tag=tag,source_status='SUPERSEDED')
        self.data['observations'][digest(tag)]={'source_tag':tag,'status':'SUPERSEDED'}
        return events

    def query(self, node_id, *, point=None, window=None):
        refs = sorted(rid for rid,r in self.data["reports"].items() if node_id in r.get("node_refs",()) and self.report_open(r))
        result = {"answer":"UNKNOWN","conflict_ref":refs}
        if node_id not in self.f_visible():
            return result
        if point is None and window is None:
            result["answer"] = "YES"
            return result
        for a in self.data["assertions"].values():
            if a["target_ref"] != node_id or not self.evidence_live({"record_id":a["assertion_id"]}):
                continue
            r = normalize(region(a["region"]))
            if point is not None:
                ok = r.kind == "POINT" and r.point == point or r.kind == "CONTINUOUS" and covers(r,TemporalRegion("POINT",point=point)) is True
            else:
                lo,hi = window
                ok = (r.kind == "POINT" and lo <= r.point <= hi or r.kind == "CONTINUOUS" and r.lo is not None and r.hi is not None and max(lo,r.lo) <= min(hi,r.hi) or r.kind == "EXISTENTIAL" and covers(TemporalRegion("CONTINUOUS",lo=lo,hi=hi),r) is True)
            if ok:
                result["answer"]="YES"
                break
        return result

    def query_support(self, support_id, *, point=None, window=None):
        """Read one path without borrowing another path's dating or bindings."""
        support=self.data['supports'].get(support_id)
        if support is None or support_id not in self.paths():
            return {'answer':'UNKNOWN','conflict_ref':[]}
        node_id=support['conclusion_ref']
        # Only assertions of this support may answer the selected path.
        result={'answer':'YES' if point is None and window is None else 'UNKNOWN',
                'conflict_ref':sorted(rid for rid,r in self.data['reports'].items()
                                      if node_id in r.get('node_refs',()) and self.report_open(r))}
        for aid,a in self.data['assertions'].items():
            if a['support_record_id']!=support_id or not self.evidence_live({'record_id':aid}): continue
            r=normalize(region(a['region']))
            if point is not None:
                ok=covers(r,TemporalRegion('POINT',point=point)) is True
            elif window is not None:
                lo,hi=window
                ok=(r.kind=='POINT' and lo<=r.point<=hi
                    or r.kind=='CONTINUOUS' and r.lo is not None and r.hi is not None and max(lo,r.lo)<=min(hi,r.hi)
                    or r.kind=='EXISTENTIAL' and covers(TemporalRegion('CONTINUOUS',lo=lo,hi=hi),r) is True)
            else: ok=True
            if ok: result['answer']='YES'; break
        return result

    def query_proposition(self,node_id,*,point=None,window=None):
        result=self.query(node_id,point=point,window=window)
        spec=self.data['nodes'].get(node_id,{})
        ck=spec.get('content_key')
        refs={rid for rid,r in self.data['reports'].items() if self.report_open(r) and any(c.get('content_key')==ck for c in r.get('candidates',()))}
        result['conflict_ref']=sorted(set(result['conflict_ref'])|refs)
        if result['answer']=='YES': return result
        if spec.get('function_id'):
            # NOT(P) shares P's conflict content key, but is a different formula.
            # A positive P path must never be borrowed as a proof of NOT(P).
            negations=[(uid,n) for uid,n in self.data['nodes'].items()
                       if n.get('function_id')=='NOT' and n.get('operands')==[node_id]]
            for uid,n in negations:
                if uid not in self.f_visible(): continue
                if point is None and window is None:
                    return {**result,'answer':'NO','evidence_ref':uid}
                wanted=TemporalRegion('POINT',point=point) if point is not None else TemporalRegion('CONTINUOUS',lo=window[0],hi=window[1])
                for aid,a in self.data['assertions'].items():
                    if a['target_ref']==uid and self.evidence_live({'record_id':aid}) and covers(region(a['region']),wanted) is True:
                        return {**result,'answer':'NO','evidence_ref':uid}
            return result
        for uid,n in self.data['nodes'].items():
            if uid==node_id or n.get('function_id') or not ck or n.get('content_key')!=ck: continue
            other=self.query(uid,point=point,window=window)
            if other['answer']=='YES':
                result.update(answer='YES',evidence_ref=uid); return result
        for uid,n in self.data['nodes'].items():
            if n.get('function_id')!='NOT' or n.get('content_key')!=ck or uid not in self.f_visible(): continue
            if point is None and window is None:
                result.update(answer='NO',evidence_ref=uid); return result
            for a in self.data['assertions'].values():
                if a['target_ref']!=uid or not self.evidence_live({'record_id':a['assertion_id']}): continue
                r=normalize(region(a['region']))
                wanted=TemporalRegion('POINT',point=point) if point is not None else TemporalRegion('CONTINUOUS',lo=window[0],hi=window[1])
                if window is not None and window[0]==window[1]: wanted=TemporalRegion('POINT',point=window[0])
                if covers(r,wanted) is True:
                    result.update(answer='NO',evidence_ref=uid); return result
        return result
