import json

import pytest

from tools.read_document_probe_mailbox import MailboxBackend


def capture(directory, ordinal, request, response):
    stem = directory / f'probe_{ordinal:04d}'
    stem.with_suffix('.request.json').write_text(json.dumps(request), encoding='utf-8')
    stem.with_suffix('.reply.txt').write_text(response, encoding='utf-8')


def test_captured_transport_requires_exact_request_and_retains_provenance(tmp_path):
    prior, current = tmp_path / 'prior', tmp_path / 'current'
    prior.mkdir(); current.mkdir()
    capture(prior, 1, {'prompt':'Choose an attachment', 'system':'Labels only'}, '0\n')
    backend = MailboxBackend(current, captured_probes=prior)
    assert backend.generate('Choose an attachment', system='Labels only') == '0\n'
    provenance = json.loads((current/'probe_0001.transport.json').read_text())
    assert provenance['mode'] == 'EXACT_CAPTURED_TRANSPORT'
    assert (current/'probe_0001.reply.txt').read_text() == '0\n'
    with pytest.raises(ValueError, match='CAPTURED_PROBE_MISSING'):
        backend.generate('Choose an attachment', system='Different instructions')
    assert not (current/'probe_0002.reply.txt').exists()


def test_conflicting_captured_replies_are_not_arbitrarily_selected(tmp_path):
    prior, current = tmp_path / 'prior', tmp_path / 'current'
    prior.mkdir(); current.mkdir()
    capture(prior, 1, {'prompt':'Choose'}, '0')
    capture(prior, 2, {'prompt':'Choose'}, '1')
    with pytest.raises(ValueError, match='CAPTURED_PROBE_AMBIGUOUS'):
        MailboxBackend(current, captured_probes=prior).generate('Choose')
    assert not (current/'probe_0001.reply.txt').exists()
