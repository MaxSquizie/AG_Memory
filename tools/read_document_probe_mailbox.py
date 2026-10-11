"""Run an arbitrary source with real V7 and an external short-probe executor.

Explicit development fixture only; no oracle cases, gold outputs or name aliases
enter this run. The executor receives request bytes and writes response bytes.
It must not inspect runtime state or construct a replacement semantic graph.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from threading import RLock
from time import monotonic, sleep
from types import SimpleNamespace


class MailboxBackend:
    model = 'external-short-probe-executor'

    def __init__(self, directory, timeout_seconds=900, captured_probes=None):
        self.directory = Path(directory)
        self.timeout_seconds = timeout_seconds
        self.ordinal = 0
        self.captured_probes = Path(captured_probes) if captured_probes else None

    def generate(self, prompt, **kwargs):
        self.ordinal += 1
        stem = self.directory / f'probe_{self.ordinal:04d}'
        request, reply = stem.with_suffix('.request.json'), stem.with_suffix('.reply.txt')
        if request.exists() or reply.exists():
            raise ValueError('PROBE_MAILBOX_ALREADY_EXISTS')
        temporary = stem.with_suffix('.request.tmp')
        temporary.write_text(json.dumps({'prompt':prompt, **kwargs}, ensure_ascii=False, indent=2), encoding='utf-8')
        temporary.replace(request)
        if self.captured_probes is not None:
            # Diagnostic transport playback, not native run-binding replay.
            # Never answer a new/different question with a previous decision.
            matches = []
            for prior in sorted(self.captured_probes.glob('probe_*.request.json')):
                if json.loads(prior.read_text(encoding='utf-8')) == {'prompt':prompt, **kwargs}:
                    response = prior.with_name(prior.name.replace('.request.json', '.reply.txt'))
                    matches.append((prior, response.read_text(encoding='utf-8')))
            if not matches:
                raise ValueError('CAPTURED_PROBE_MISSING: exact request not present')
            if len({value for _, value in matches}) != 1:
                raise ValueError('CAPTURED_PROBE_AMBIGUOUS: recorded replies disagree')
            prior, value = matches[0]
            reply.write_text(value, encoding='utf-8')
            stem.with_suffix('.transport.json').write_text(json.dumps({
                'mode':'EXACT_CAPTURED_TRANSPORT', 'request_source':str(prior),
                'request_sha256':hashlib.sha256(prior.read_bytes()).hexdigest(),
                'response_sha256':hashlib.sha256(value.encode('utf-8')).hexdigest(),
            }, indent=2), encoding='utf-8')
            return value
        print(json.dumps({'event':'probe_pending','request_path':str(request),
                          'reply_path':str(reply)}), flush=True)
        started = monotonic()
        while not reply.exists():
            if (self.directory / 'CANCEL').exists():
                raise RuntimeError('PROBE_EXECUTOR_CANCELLED')
            if monotonic()-started > self.timeout_seconds:
                raise TimeoutError('PROBE_EXECUTOR_TIMEOUT')
            sleep(.1)
        return reply.read_text(encoding='utf-8')


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--development-fixture',action='store_true',required=True,
                        help='Explicit TEST_ONLY resource release in a new isolated AH; never production validation')
    parser.add_argument('--captured-probes',type=Path,
                        help='Exact recorded request/reply pairs for transport diagnostics; not a live model or canonical replay')
    parser.add_argument('--components',action='store_true',
                        help='Use the explicit TEST_ONLY COMPONENTS_V1 policy (new resource hash)')
    parser.add_argument('--relative-time',action='store_true',help='TEST_ONLY released event-relative adjunct rules; requires --components')
    parser.add_argument('--verify-replay',action='store_true',help='Repeat the same source in the same runtime; verify no new calls/ticks/ledger changes')
    args=parser.parse_args(argv)
    if args.relative_time and not args.components: parser.error('--relative-time requires --components')
    args.out.mkdir(parents=True,exist_ok=False)
    from ah.core import AHCore
    from ah.core.journal import JournalChannel
    from ah.agent import InteractionContext
    from ah.model import Domain
    from ah.config import IgnitionSettings, WorkspaceSettings, IntegrationSettings
    from ah.documents import DocumentProcessor
    from ah.documents.reading import read_document
    from ah.formalizer.runtime_adapter import FormalizerAdapter
    from ah.formalizer.real_backend import RealBackendSelector
    from ah.formalizer.run_binding import InterpretationRunBinding
    from ah.formalizer.ah_adapter import AHStoreAdapter
    from ah.formalizer.pipeline import MorphProvider
    from ah.ignition import IgnitionEngine
    from ah.integration.service import IntegrationConfig, IntegrationService
    from ah.perception.llm_parser import LLMPerceptionService, LLMPerceptionSettings
    from tools.formalizer_v7_native_binding import fixture

    core=AHCore()
    release,_=fixture(core,'known')
    if args.components:
        from tools.formalizer_component_fixture import with_components
        release=with_components(release,relative_time=args.relative_time)
    (args.out/'resource_manifest.json').write_text(json.dumps(release.manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    (args.out/'experiment.json').write_text(json.dumps({
        'resource_status':'TEST_ONLY_COMPONENTS' if args.components else 'TEST_ONLY_EXISTING_FIXTURE','production_validation':False,
        'source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'entity_bindings':'NO_ORACLE_ALIASES','provider':MailboxBackend.model,
        'transport':'EXACT_CAPTURED_TRANSPORT' if args.captured_probes else 'EXTERNAL_EXECUTOR',
        'captured_probes':str(args.captured_probes) if args.captured_probes else None},indent=2),encoding='utf-8')
    journal=JournalChannel(args.out/'journal.log')
    store=AHStoreAdapter(core.store,journal,core=core)
    binding=InterpretationRunBinding(journal)
    ignition=IgnitionEngine(core,IgnitionSettings(),WorkspaceSettings(.02))
    backend=MailboxBackend(args.out,captured_probes=args.captured_probes)
    selector=RealBackendSelector(backend,journal=journal,model_key=MailboxBackend.model)
    adapter=FormalizerAdapter(selector,morph=MorphProvider(),store=store,binding=binding,release=release,ignition=ignition)
    perception=LLMPerceptionService(None,LLMPerceptionSettings(),formalizer=adapter,native_commit=True)
    services=SimpleNamespace(core=core,ignition=ignition,perception=perception,
        integration=IntegrationService(core,IntegrationConfig.from_settings(IntegrationSettings())),
        operation_lock=RLock(),context=InteractionContext(user_ref=core.ref(core.add_entity(Domain.C).uid)))
    services.document_processor=lambda:DocumentProcessor(services)
    report=read_document(services,args.source,args.out/'reading',
        progress=lambda event:print(json.dumps(event,ensure_ascii=False),flush=True))
    print(json.dumps({'event':'completed','status':report['status'],
                      'report_path':str(args.out/'reading/report.json')},ensure_ascii=False),flush=True)
    if args.verify_replay and report['status']=='EXECUTED':
        from tools.document_replay_check import verify
        if not verify(services,args.source,args.out,report,backend,store): return 1
    return 0 if report['status']=='EXECUTED' else 1


if __name__=='__main__':
    raise SystemExit(main())
