"""Lossless presentation only: no candidate admission, identity or truth inference."""
from os.path import commonprefix


def factor_options(options):
    """Move a shared description prefix out of repeated option text.

    Reconstruction is checked byte for byte. This is NOT equivalence: candidate
    IDs and their complete domain remain unchanged, and duplicate labels are
    rejected by the caller before rendering. A singleton is still a proposal.
    """
    if len(options)<2:return options,''
    labels=[o['label'] for o in options]
    prefix=commonprefix(labels)
    end=prefix.rfind('; ')
    if end<0:return options,''
    prefix=prefix[:end+2]
    if not prefix.strip() or any(not s[len(prefix):].strip() for s in labels):return options,''
    rendered=[{**o,'label':o['label'][len(prefix):]} for o in options]
    assert all(prefix+r['label']==o['label'] for r,o in zip(rendered,options))
    return rendered,prefix[:-2]


def readable_memory(rows,proofs):
    """Proof provenance remains in context_reads; language gets evidence only."""
    import json
    values=[]
    for row in rows:
        item={k:row[k] for k in ('label','features','source_context','reference_kind') if row.get(k)}
        if item:values.append(item)
    # Conclusions may contain symbolic facts, but never receipt hashes or chains.
    conclusions=[p.get('conclusion') or p.get('proof',{}).get('conclusion') for p in proofs]
    return json.dumps({'context':values,'established_conclusions':[c for c in conclusions if c]},
                      ensure_ascii=False,sort_keys=True) if values or any(conclusions) else ''
