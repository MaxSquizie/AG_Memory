"""Render typed runtime answers without promoting partial results to facts."""
def question_text(outcome,semantic,core):
    result=outcome.conclusion; p=result.payload
    def ref(uid):
        return semantic.inference_text_for_ref(core.ref(uid)) if core.store.has_uid(uid) else str(uid)
    prefix=result.kind+': '+outcome.status.value+'. '
    if result.kind=='WHEN':
        rows=[]
        for a in p['evidences']:
            r=a['region']
            detail=('момент '+str(r['point']) if r['kind']=='POINT' else
                    'непрерывно в '+str((r['lo'],r['hi'])) if r['kind']=='CONTINUOUS' else
                    'в некоторый неизвестный момент внутри '+str((r['lo'],r['hi'])))
            rows.append(detail+'; '+('свидетельство '+a['assertion_id'] if 'assertion_id' in a else 'временное доказательство в области запроса'))
        return prefix+('; '.join(rows) if rows else 'Временное свидетельство отсутствует.')
    if result.kind=='WHY':
        path=p.get('path',[])
        return prefix+('; '.join(ref(e['cause_ref'])+' → '+ref(e['effect_ref']) for e in path) if path else 'Причинное доказательство отсутствует.')
    if result.kind=='COMPARE':
        return prefix+(ref(p['left_ref'])+' '+p['ordering']+' '+ref(p['right_ref'])+
                       '; значения '+str(p['left_values'])+' и '+str(p['right_values'])+' '+p['unit'])
    candidates=', '.join(ref(uid) for uid in p.get('candidate_refs',()))
    scope='; область сравнения '+str(p.get('comparison_regions',[]))
    if result.complete:
        return prefix+'Экстремум '+str(p.get('value'))+' '+p['unit']+'; '+candidates+scope
    return prefix+'Лучшие среди доказанных кандидатов: '+(candidates or 'нет')+'; полнота области сравнения не доказана.'+scope
