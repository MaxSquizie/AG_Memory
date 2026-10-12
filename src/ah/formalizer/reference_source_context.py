"""Verbatim evidence excerpts for already selected active-memory candidates."""
import re


def attach(store, rows):
    wanted={tuple(r['source_tag']) for r in rows}
    texts={}
    for record in store._journal.scan_unprocessed(0,payload_kinds={'run_bind'}):
        p=record['payload'];tag=(p.get('observation_id'),p.get('version'))
        if p.get('kind')=='run_bind' and tag in wanted:
            texts[tag]=(p.get('snapshot_data') or {}).get('text','')
    for row in rows:
        text=texts.get(tuple(row['source_tag']),'')
        binding=store.ledger.data['bindings'][row['memory_binding_ref']]
        anchors=[binding.get('mention_ref','')]
        for sid in row.get('premise_support_refs',()):
            support=store.ledger.data['supports'].get(sid,{})
            node=store.ledger.data['nodes'].get(support.get('conclusion_ref'),{})
            anchors.append(node.get('source_ref',''))
        spans=[]
        for anchor in anchors:
            match=re.fullmatch(r'tok:(\d+):(\d+)',anchor)
            if match:
                lo,hi=map(int,match.groups())
                if 0<=lo<hi<=len(text):spans.append((lo,hi))
        if spans:
            lo,hi=spans[0]
            lo,hi=max(0,lo-96),min(len(text),hi+96)
            row['memory_excerpt']=text[lo:hi]
            row['memory_excerpt_range']=[lo,hi]
            row['label'] += '; source excerpt: '+text[lo:hi]
