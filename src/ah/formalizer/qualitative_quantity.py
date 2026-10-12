"""Released qualitative nominal groups; lexical quantity never becomes a number."""
from dataclasses import replace
from .canonical_ledger import digest
from .component_policy import _morph
from .component_probe import _probe
from .state import MorphVariant


def validate(cfg):
    policy = cfg.get('qualitative_quantity')
    if not policy:
        return
    rows = policy['rules']
    if (cfg.get('nominal_composition') != 'QUESTION_TREE_V1' or
            len({r['rule_id'] for r in rows}) != len(rows) or
            len({(r['lemma'],r['POS']) for r in rows}) != len(rows) or
            any(not r['lemma'].strip() or r['lemma'] != r['lemma'].casefold() for r in rows)):
        raise ValueError('invalid qualitative quantity policy')


def agrees(predicate):
    return (predicate.person in {None, '3rd'} and (predicate.number == 'plur' or
            predicate.number == 'sing' and predicate.gender in {None, 'neut'}))


def resolve(state, release, selector, region, tokens, cfg):
    policy = cfg.get('qualitative_quantity', {})
    if policy.get('version') != 'LEXICAL_GROUP_V1':
        return tokens, []
    state.require_structures_open('QUALITATIVE_QUANTITY')
    groups, readings = [], {}
    for marker, head in zip(tokens, tokens[1:]):
        rules = [r for r in policy['rules'] if any(v.lemma == r['lemma'] and
                 v.pos == r['POS'] for v in marker.variants)]
        nouns = [v for v in head.variants if v.pos == 'NOUN' and v.number == 'plur' and 'gen' in v.cases]
        if not rules or not nouns:
            continue
        if region.source_range[1]-region.source_range[0] > cfg['context_chars']:
            state.diag('COMPONENT_SEARCH_INCOMPLETE', region.region_id)
            return None, []
        # Multiple resource interpretations are not silently ordered by priority.
        if len(rules) != 1 or len({v.lemma for v in nouns}) != 1:
            state.diag('QUALITATIVE_QUANTITY_UNRESOLVED', region.region_id)
            return None, []
        rule = rules[0]
        variants = [v for v in marker.variants if v.lemma == rule['lemma'] and v.pos == rule['POS']]
        cases = sorted({c for v in variants for c in v.cases if c in {'nom', 'acc'}})
        if not cases:
            continue
        key = region.region_id+'|quantity:'+digest([marker.token_id, head.token_id, rule])
        previous = state.decisions.get(key)
        choice = previous.selected[0] if previous and previous.outcome == 'RESOLVED' and len(previous.selected) == 1 else None
        if previous is None:
            choice = _probe(state, selector, release, key, 'nominal_attachment', [
                {'candidate_id':'GROUP', 'label':'«'+marker.span+' '+head.span+'»: quantity word describes this plural nominal group; members and numeric cardinality unspecified'},
                {'candidate_id':'OTHER', 'label':'The quantity word does not describe this nominal group; retain original analyses'}],
                state.text[slice(*region.source_range)], region.source_range,
                question='Does the quantity expression describe the adjacent plural noun, rather than the degree of an action? Choose only from source wording; do not assign numbers.')
        if choice is None:
            state.diag('QUALITATIVE_QUANTITY_UNRESOLVED', region.region_id)
            return None, []
        if choice != 'GROUP':
            continue
        row = {'head_ref':head.token_id, 'marker_ref':marker.token_id,
               'decision_ref':key, 'rule_id':rule['rule_id'], 'resource_sha256':release.sha256,
               'marker_variants':[_morph(v) for v in variants], 'internal_readings':[_morph(v) for v in nouns],
               'raw':state.text[marker.start:head.end], 'source_range':[marker.start, head.end]}
        groups.append(row)
        # External case belongs to the WHOLE phrase. The noun's genitive R1
        # readings remain immutable in evidence and in internal_readings.
        # Aggregate agreement permits singular/neuter or plural predicates;
        # it does not invent gender or individual participants.
        readings[head.token_id] = tuple(MorphVariant(nouns[0].lemma, 'NOUN', frozenset({c}),
            features=frozenset({'NOUN','QUALITATIVE_GROUP'}), origin='CONTEXTUAL',
            evidence_refs=(key, marker.token_id, head.token_id)) for c in cases)
        state.syntax_trace.append({'kind':'QUALITATIVE_QUANTITY', **row, 'external_cases':cases})
    return [replace(t, variants=readings[t.token_id]) if t.token_id in readings else t for t in tokens], groups


def units(tokens, missing, frame):
    evidence = {e.token_id:e for e in tokens}
    for row in frame.semantic.get('qualitative_groups', ()):
        head, marker = row['head_ref'], row['marker_ref']
        if marker not in missing or head not in frame.semantic['proposed_roles']:
            continue
        cases = set(frame.semantic['morph_bindings'][head]['cases'])
        unique = {}
        for raw in row['marker_variants']:
            if not cases.intersection(raw['cases']):
                continue
            v = MorphVariant(**{**raw, 'cases':frozenset(raw['cases']),
                'features':frozenset(raw['features']), 'evidence_refs':tuple(raw['evidence_refs'])})
            unique[digest({k:v for k,v in raw.items() if k not in {'score','features'}})] = v
        for v in unique.values():
            yield {'token':evidence[marker], 'variant':v, 'refs':(marker,), 'entities':[],
                   'adjectives':[], 'bound_host':head, 'host_reading':frame.semantic['morph_bindings'][head]}
