"""Declared re-interpretation of the frozen observation on a reviewed release.

LinkOpenTemplate records are audit evidence, never aliases used by inference.
The replacement and retirement are committed together by native T6.
"""
from __future__ import annotations
from copy import deepcopy
from .canonical_ledger import digest


def reinterpret_observation(store,binding,selector,release,*,observation_id,
                            previous_version,trigger_ref,open_template_links=(),morph=None):
    from .v7_pipeline import interpret_full
    release.assert_integrity()
    if not isinstance(trigger_ref,str) or not trigger_ref or type(previous_version) is not int or previous_version<1:
        raise ValueError('DECLARED_TRIGGER_REQUIRED')
    with store._journal.atomic(),store._store._lock:
        store._refresh()
        previous=store.ledger.data['observations'].get(digest([observation_id,previous_version]))
        marker=digest({'observation_id':observation_id,'interpretation_version':previous_version+1})
        replay=marker in store.ledger.data['markers']
        if not previous or previous['status']!='LIVE' and not replay: raise ValueError('MIGRATION_SOURCE_STALE')
        raw=binding.input_snapshot(observation_id,previous_version)
        if raw is None: raise ValueError('MIGRATION_INPUT_MISSING')
        raw=deepcopy(raw)
    if replay:
        replacement=binding.input_snapshot(observation_id,previous_version+1)
        if replacement is None or replacement.get('trigger_ref')!=trigger_ref or replacement.get('open_template_links',[])!=list(open_template_links):
            raise ValueError('MIGRATION_REPLAY_MISMATCH')
        raw=deepcopy(replacement)
    raw.pop('rx_reads',None)  # interpret_full restores frozen replacement reads on replay
    raw.update(supersedes_version=previous_version,trigger_ref=trigger_ref,
               open_template_links=deepcopy(list(open_template_links)))
    return interpret_full(raw['text'],None,selector,store,binding,release=release,
                          version=previous_version+1,observation_id=observation_id,
                          raw_input=raw,context_facts=tuple(raw.get('context_facts',())),morph=morph)
