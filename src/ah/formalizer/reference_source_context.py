"""Verbatim evidence excerpts for already selected active-memory candidates."""
import re


def attach(store, rows):
    if not rows:return
    wanted={tuple(r['source_tag']) for r in rows}
    texts={}
    for record in store._journal.scan_unprocessed(0,payload_kinds={'run_bind'}):
        p=record['payload'];tag=(p.get('observation_id'),p.get('version'))
        if p.get('kind')=='run_bind' and tag in wanted:
            texts[tag]=(p.get('snapshot_data') or {}).get('text','')
    for row in rows:
        text=texts.get(tuple(row['source_tag']),'')
        # The short excerpt locates an anchor; it cannot stand in for the
        # original envelope when a qualification lies outside that window.
        row['source_context']=text
        row['source_context_complete']=bool(text)
        event=row.get('reference_kind')=='EVENT'
        binding={} if event else store.ledger.data['bindings'][row.get('memory_binding_ref',row.get('binding_ref'))]
        entity=None if event else store._store.get_element_any_domain(row['entity_ref'])
        implicit=entity.meta.get('implicit_participant') if entity is not None else None
        if implicit is not None:
            row['label']='Previously grounded omitted '+implicit['participant_kind'].lower()+' (identity unidentified)'
            row['implicit_participant']=dict(implicit)
        anchors=[row.get('source_ref') or '',binding.get('mention_ref','')]
        placeholder=entity.meta.get('referential_placeholder') if entity is not None else None
        if placeholder is not None:
            constraint=placeholder['constraint']
            row['referential_placeholder']=dict(placeholder)
            row['label']='Previously introduced referent «'+constraint['raw']+'» (identity/details unknown; this is an existing referent, not a new object)'
            anchors.insert(0,constraint['head_ref'])
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
            row['memory_anchor_range']=[lo,hi]
            row['memory_anchor_text']=text[lo:hi]
            lo,hi=max(0,lo-96),min(len(text),hi+96)
            row['memory_excerpt']=text[lo:hi]
            row['memory_excerpt_range']=[lo,hi]
            row['label'] += '; source excerpt: '+text[lo:hi]
