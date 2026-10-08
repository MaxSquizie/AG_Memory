"""Append-only provider exchange history; ordinal is distinct from retry attempt."""
from contextlib import nullcontext
from threading import RLock


class ProviderCallLog:
    def __init__(self,journal=None):
        self._journal=journal; self._calls={}; self._lock=RLock()
        self._reload()

    def _reload(self):
        if self._journal:
            calls={}
            for r in self._journal.scan_unprocessed(0):
                p=r['payload']
                if p.get('kind')!='prov_call': continue
                previous=calls.get(p['id'])
                if previous:
                    identity=('provider','run_id','ordinal','attempt','request_digest','model_key','params_hash','prompt')
                    if any(p.get(k)!=previous.get(k) for k in identity): raise ValueError('INTEGRITY_ERROR: provider exchange identity changed')
                    if previous['state']!='PENDING' and p!=previous or p['state'] not in {'PENDING','RECEIVED','FAILED'}:
                        raise ValueError('INTEGRITY_ERROR: provider terminal rewrite')
                elif p.get('state')!='PENDING': raise ValueError('INTEGRITY_ERROR: provider exchange without PENDING')
                calls[p['id']]=dict(p)
            self._calls=calls

    def lookup(self,run_id,ordinal):
        self._reload()
        values=[r for r in self._calls.values() if r.get('run_id')==run_id and r.get('ordinal')==ordinal]
        return max(values,key=lambda r:r['attempt']) if values else None

    def begin(self,provider,request_digest,*,run_id='legacy',ordinal=None,model_key='',params_hash='',prompt=''):
        with self._lock,(self._journal.atomic() if self._journal else nullcontext()):
            self._reload()
            if ordinal is None:
                ordinal=max((r.get('ordinal',0) for r in self._calls.values() if r.get('run_id')==run_id),default=0)+1
            old=self.lookup(run_id,ordinal)
            if old and (old['request_digest'],old.get('model_key',''),old.get('params_hash',''))!=(request_digest,model_key,params_hash):
                raise ValueError('REPLAY_MISMATCH')
            attempt=(old['attempt']+1) if old else 1
            call_id=f'{run_id}:{provider}:{ordinal}:{attempt}'
            rec={'kind':'prov_call','id':call_id,'provider':provider,'run_id':run_id,'ordinal':ordinal,'attempt':attempt,'request_digest':request_digest,'model_key':model_key,'params_hash':params_hash,'prompt':prompt,'state':'PENDING'}
            if self._journal: self._journal.append('provider',rec,run_id=run_id)
            self._calls[call_id]=rec
            return call_id

    def _transition(self,call_id,state,**extra):
        with self._lock,(self._journal.atomic() if self._journal else nullcontext()):
            self._reload(); old=self._calls.get(call_id)
            if old is None: return False
            if old['state']!='PENDING':
                if old['state']==state and all(old.get(k)==v for k,v in extra.items()): return True
                raise ValueError('PROVIDER_TERMINAL_REWRITE')
            rec={**old,**extra,'state':state}
            if self._journal: self._journal.append('provider',rec,run_id=rec['run_id'])
            self._calls[call_id]=rec
            return True

    def received(self,call_id,response_digest=None,*,raw_response=None,response_time_ms=None):
        return self._transition(call_id,'RECEIVED',response_digest=response_digest,raw_response=raw_response,response_time_ms=response_time_ms)

    def failed(self,call_id,error=''):
        return self._transition(call_id,'FAILED',error=error)

    def state(self,call_id):
        self._reload(); r=self._calls.get(call_id)
        return r['state'] if r else None
