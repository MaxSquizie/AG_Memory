from ah.model import Domain

from .rules import known_forms, name_type


def _noun_reading(row, proper):
    form = row.get('morphology') or {}
    if form.get('pos') != 'NOUN' or form.get('number') != 'sing' or form.get('case') != 'nomn':
        return False
    tags = [tag for lemma, tag in known_forms(row['surface'])
            if lemma == row['lemma'] and tag.POS == 'NOUN'
            and all(not form.get(key) or form[key] == getattr(tag, key)
                    for key in ('number', 'case', 'gender', 'animacy'))]
    return bool(tags) and all(bool(name_type(tag) or tag.grammemes & {'Geox', 'Orgn', 'Trad'}) == proper
                              for tag in tags)


def _direct_class(store, observation, subject, predicate):
    polarity = observation.meta.get('root_status')
    if observation.meta.get('kind') != 'russian_grammar.observation' or polarity not in ('asserted', 'negated'):
        return None
    if subject not in observation.members or predicate not in observation.members:
        return None
    pred_index = observation.members.index(predicate)
    has_negation = False
    for ref in observation.members:
        row = store.get_element(Domain.H, ref.uid).meta
        if row.get('assertion_status') != polarity or row.get('assertion_context') or 'quotation' in row:
            return None
        if ref == predicate:
            if row['role'] != 'predicate' or row['head'] is not None or row.get('rule') != 'V2':
                return None
            if row.get('scope') != ('negated' if polarity == 'negated' else None) or not _noun_reading(row, False):
                return None
        elif row.get('head') != pred_index or store.find_link('grammar.' + row['role'], ref.uid, predicate.uid) is None:
            return None
        elif ref == subject:
            if row['role'] != 'subject' or row.get('scope') or not _noun_reading(row, True):
                return None
        elif row['role'] == 'particle' and row['lemma'] == 'не' and polarity == 'negated':
            has_negation = True
        elif row['role'] != 'punctuation':
            return None
    if has_negation != (polarity == 'negated'):
        return None
    return polarity


def classes(core, name_lemma):
    store = core.store
    assertions = {}
    denials = set()
    for uid in store.subject_occurrences(name_lemma):
        for edge in store.outgoing_links(uid, 'grammar.subject'):
            for observation in store.groups_containing(edge.target.uid):
                polarity = _direct_class(store, observation, edge.source, edge.target)
                if polarity:
                    lemma = store.get_element(Domain.H, edge.target.uid).meta['lemma']
                    if polarity == 'negated':
                        denials.add(lemma)
                    else:
                        assertions.setdefault(lemma, observation.uid)
    return tuple((lemma, uid) for lemma, uid in assertions.items() if lemma not in denials)
