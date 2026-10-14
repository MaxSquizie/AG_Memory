"""Read-only index of native observations; human notes never change AH."""
from dataclasses import dataclass
from hashlib import sha256
import json


@dataclass
class Entry:
    category: str
    ref: str
    label: str
    status: str
    record: dict
    source_range: object = None


class Inspection:
    def __init__(self,snapshot):
        if not isinstance(snapshot,dict):raise ValueError('Expected a native snapshot object')
        self.snapshot=snapshot;self.state=snapshot.get('state',{})
        self.text=snapshot.get('source_text',self.state.get('text',''))
        self.source_sha256=sha256(self.text.encode('utf-8')).hexdigest()
        self.entries=[];self.by_ref={}
        regions={r['region_id']:r for r in (self.state.get('region_forest') or {}).get('regions',())}
        evidence={e['token_id']:e for e in self.state.get('evidence',())}
        def add(category,ref,label,status,record,bounds=None):
            item=Entry(category,str(ref),str(label),str(status or ''),record,bounds)
            self.entries.append(item);self.by_ref.setdefault(str(ref),item)
        for ref,r in regions.items():add('Области',ref,r['kind'],'',r,r.get('source_range'))
        for ref,e in evidence.items():add('Морфология',ref,e['span'],'',e,[e['start'],e['end']])
        for f in self.state.get('frames',()):
            sem=f.get('semantic',{});status=sem.get('structural_rejection') or ('UNRESOLVED' if sem.get('structural_unresolved') else 'CANDIDATE')
            add('Фреймы',f['frame_id'],f.get('anchor_span',''),status,f,f.get('source_range'))
        formulas=list(self.state.get('logical_roots',()))
        for f in self.state.get('frames',()):
            sem=f.get('semantic',{})
            for i,tree in enumerate(sem.get('operator_forest',())):
                add('Формулы',f['frame_id']+'|tree:'+str(i),tree.get('operator','frame'),'STRUCTURE ≠ FACT',tree,(tree.get('scope_boundary') or {}).get('source_range') or f.get('source_range'))
        for i,tree in enumerate(formulas):add('Формулы','logical:'+str(i),tree.get('operator','root'),'STRUCTURE ≠ FACT',tree)
        for key,d in self.state.get('decisions',{}).items():
            bounds=(regions.get(key.split('|')[0]) or {}).get('source_range')
            frame=self.by_ref.get(d.get('frame_id'))
            add('Решения',key,d.get('slot_id',''),d.get('outcome'),d,bounds or (frame.source_range if frame else None))
        for key,r in self.state.get('component_probe_records',{}).items():
            d=r.get('decision',{});entry=self.by_ref.get(key)
            add('Пробы',key+'|probe',d.get('slot_id',''),
                'SUPERSEDED' if r.get('superseded_by') else d.get('selector_outcome'),r,entry.source_range if entry else None)
        for i,r in enumerate(self.state.get('syntax_trace',())):
            kind=r.get('kind',r.get('event','TRACE'));category='Границы условий' if kind=='SCOPE_BOUNDARY' else 'Трасса'
            bounds=r.get('source_range') or (regions.get(r.get('region_ref',r.get('owner_region'))) or {}).get('source_range')
            refs=r.get('owned_token_refs',())
            selected=[evidence[t] for t in refs if t in evidence]
            if not bounds and selected:bounds=[min(t['start'] for t in selected),max(t['end'] for t in selected)]
            label=(r.get('operator','')+' '+str(bounds)) if category=='Границы условий' else kind
            add(category,r.get('boundary_ref','trace:'+str(i)),label,r.get('event',r.get('coverage','')),r,bounds)
        from ah.documents.reading_coverage import frame_anchors
        anchored=frame_anchors(self.state.get('frames',()))
        for ref,e in evidence.items():
            if ref not in anchored:add('Без привязки',ref+'|unanchored',e['span'],'UNANCHORED ≠ ERROR',e,[e['start'],e['end']])
        for i,d in enumerate(self.state.get('diagnostics',())):
            add('Диагностика','diagnostic:'+str(i),d.get('code',''),'',d)
        for i,r in enumerate(self.state.get('context_reads',())):add('Контекст','context:'+str(i),r.get('kind','READ'),'',r)
        observation=self.state.get('observation',{})
        for kind in ('entity_bindings','implicit_bindings','event_bindings','local_reference_targets'):
            for ref,value in observation.get(kind,{}).items():
                record={'kind':kind,'target':value}
                add('Привязки',str(ref)+'|binding',ref,'RESOLVED REFERENCE ≠ FACT',record)
        graph=snapshot.get('committed_graph',{})
        for ref,node in graph.get('nodes',{}).items():
            source=evidence.get(node.get('source_ref'))
            bounds=[source['start'],source['end']] if source else None
            label=node.get('function_id') or node.get('proposition',{}).get('predicate') or node.get('name') or ref
            status='RECEIPT' if ref in graph.get('receipt_refs',()) else 'STRUCTURAL DESCENDANT'
            add('Граф AH',ref,label,status,node,bounds)
        if graph.get('truncated'):
            add('Диагностика','graph-limit','Проекция графа ограничена','TRUNCATED',{'remaining_refs':graph['remaining_refs']})
        add('Результат','runtime-configuration','Backend / модель','CONFIGURATION',snapshot.get('runtime_configuration',{}))
        add('Результат','receipt','Commit receipt',snapshot.get('commit_receipt',{}).get('terminal'),snapshot.get('commit_receipt',{}))
        if snapshot.get('diagnostic_error'):add('Диагностика','observer-error','Ошибка экспорта IR','ERROR',snapshot['diagnostic_error'])

    def page(self,category='',query='',offset=0,size=150):
        query=query.casefold();matches=(e for e in self.entries if (not category or e.category==category)
            and (not query or query in (e.ref+' '+e.label+' '+e.status).casefold()))
        result=[];count=0
        for e in matches:
            if offset<=count<offset+size:result.append(e)
            count+=1
        return result,count

    def links(self,entry):
        found=set();pending=[entry.record];budget=10000
        while pending and budget:
            value=pending.pop();budget-=1
            if isinstance(value,str) and value in self.by_ref and value!=entry.ref:found.add(value)
            elif isinstance(value,dict):pending.extend(value.values())
            elif isinstance(value,list):pending.extend(value)
        return sorted(found)

    def note(self,entry,text,verdict):
        if not text.strip():raise ValueError('Добавьте описание замечания')
        return {'ref':entry.ref,'category':entry.category,'source_range':entry.source_range,
                'source_sha256':self.source_sha256,'verdict':verdict,'comment':text.strip(),
                'observation_id':self.snapshot.get('commit_receipt',{}).get('observation_id'),
                'structural_hash':self.state.get('structural_hash'),'authority':'HUMAN_REVIEW_ONLY'}


def preview(value,limit=100000):
    parts=[];length=0
    for chunk in json.JSONEncoder(ensure_ascii=False,indent=2).iterencode(value):
        room=limit-length
        if len(chunk)>room:
            parts.append(chunk[:room]);parts.append('\n… предпросмотр сокращён; экспорт содержит полный объект.');break
        parts.append(chunk);length+=len(chunk)
    return ''.join(parts)
