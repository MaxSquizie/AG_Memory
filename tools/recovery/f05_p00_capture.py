"""Read-only pytest profiler for P00; F05_CAPTURE_OUTPUT selects the evidence file."""
import sys,json,pathlib,os
from copy import deepcopy
rows=[];current=None;active={}
def profile(frame,event,arg):
    global current
    if current is None:return
    name=frame.f_code.co_name;file=frame.f_code.co_filename
    if event=='return' and name=='generate' and file.endswith('test_structural_relation_tasks.py'):
        current['probes'].append({'prompt':str(frame.f_locals.get('prompt')),'response':arg,'errors':list(frame.f_locals['self'].errors),'remaining':list(frame.f_locals['self'].steps)})
    if event=='return' and name=='_probe' and file.endswith('/component_probe.py'):
        s=frame.f_locals.get('state');key=frame.f_locals.get('key')
        current['probe_returns'].append({'key':key,'slot':frame.f_locals.get('slot'),'result':arg,'trace':deepcopy(s.syntax_trace[-3:]),'decision':deepcopy(vars(s.decisions[key])) if key in s.decisions else None})
    if event=='return' and name=='execute_native' and file.endswith('formalizer_v7_native_binding.py'):
        current['native'].append(deepcopy(arg))
        session=frame.f_locals.get('session')
        current.setdefault('release_hashes',[]).append(getattr(getattr(session,'release',None),'sha256',None))
def pytest_runtest_setup(item):
    global current
    current={'nodeid':item.nodeid,'probes':[],'probe_returns':[],'native':[]};sys.setprofile(profile)
def pytest_runtest_logreport(report):
    global current
    if report.when=='call':
        sys.setprofile(None);current['outcome']=report.outcome;current['failure']=str(report.longrepr) if report.failed else None
        rows.append(current);pathlib.Path(os.environ.get('F05_CAPTURE_OUTPUT','/tmp/f05_p00_capture.json')).write_text(json.dumps(rows,ensure_ascii=False,default=lambda v:vars(v) if hasattr(v,'__dict__') else str(v),indent=2));current=None
