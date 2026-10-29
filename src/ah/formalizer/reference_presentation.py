"""Present existing reference evidence without deciding identity or roles."""


def label(state, rows):
    """Keep all distinct source descriptions of a target, not only rows[0].

    Offsets address occurrences; they are not evidence for choosing the nearer
    one. Missing semantic distinctions remain unknown, never invented from IDs.
    """
    evidence={t.token_id:t for t in state.evidence}
    descriptions=[]
    for row in rows:
        parts=[row['label'], 'type='+row.get('reference_kind','ENTITY')]
        refs=[row.get('local_anchor_ref'),row.get('head_ref')]
        refs.extend(m.get('source_token_ref') or m.get('mention_ref') for m in row.get('members',()))
        anchors=list(dict.fromkeys(r for r in refs if r in evidence))
        for ref in anchors:
            token=evidence[ref]
            lo,hi=max(0,token.start-96),min(len(state.text),token.end+96)
            parts.append('Current-source occurrence «'+token.span+'» at characters '+
                str(token.start)+':'+str(token.end)+'; surrounding source: «'+state.text[lo:hi]+'»')
        excerpt=row.get('memory_excerpt')
        if excerpt and excerpt not in row['label']:
            parts.append('Source excerpt: «'+excerpt+'»')
        if row.get('memory_excerpt_range'):
            parts.append('Excerpt character range: '+str(row['memory_excerpt_range']))
        if row.get('memory_anchor_range'):
            parts.append('Referenced source occurrence «'+row.get('memory_anchor_text','')+
                '» at characters '+str(row['memory_anchor_range']))
        if row.get('source_context'):
            parts.append('Source context: '+str(row['source_context']))
        elif row.get('source_context_complete') is False:
            parts.append('Original source context unavailable; do not infer omitted facts')
        description='; '.join(parts)
        if description not in descriptions:descriptions.append(description)
    return ' | Another grounding description of the SAME referent: '.join(descriptions)
