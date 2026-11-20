from itertools import product
from math import prod

from . import distribution_graph
from .distribution_membership import classes


def _candidates(core, question, root):
    records = {}
    for i, row in enumerate(question):
        prep = row.get('head') if row['role'] == 'governed' else None
        if prep is not None and question[prep]['role'] != 'preposition':
            continue
        if ((prep is None and row.get('head') != root)
                or row['role'] not in ('subject', 'object', 'recipient', 'oblique', 'beneficiary',
                                       'agent', 'experiencer', 'stimulus', 'governed')
                or row.get('implicit') or row.get('scope') or row.get('quantity_kind')
                or (row.get('morphology') or {}).get('pos') != 'NOUN'):
            continue
        name = row['lemma']
        for group, rows, frame, domain, member in distribution_graph.lookup(core, name):
            _add(records, question, root, i, group, rows, frame, domain, ())
        for restriction, ref in classes(core, name):
            for g, rows, frame, d in distribution_graph.lookup_class(core, restriction):
                _add(records, question, root, i, g, rows, frame, d, (ref,))
    return records.values()


def _add(records, question, root, i, group, rows, frame, domain_index, support):
    domain = frame.domains[domain_index]
    row = question[i]
    if (domain.role != row['role'] or rows[frame.predicate]['lemma'] != question[root]['lemma']
            or any(part.get('head') == i and part['role'] != 'punctuation' for part in question)):
        return
    if domain.role == 'governed':
        prep = rows[domain.head].get('head')
        if prep is None or rows[prep]['lemma'] != question[row['head']]['lemma']:
            return
    if domain.role in ('oblique', 'governed') and rows[domain.head].get('case') != row.get('case'):
        return
    entry = records.setdefault((group.uid, frame), (group, rows, frame, [dict() for _ in frame.domains]))
    entry[3][domain_index].setdefault(i, support)


def _instance(question, root, stored, frame, args):
    from .memory import _compatible

    pred = frame.predicate
    variable_subject = any(d.role == 'subject' for d in frame.domains)
    if (stored[pred]['role'] != 'predicate' or stored[pred]['head'] is not None
            or any(row.get('assertion_status') != 'asserted' or 'quotation' in row for row in question)
            or not _compatible(question, root, stored[pred], False, True, variable_subject)):
        return None
    instance = list(stored)
    for domain, arg in zip(frame.domains, args):
        head = domain.head
        instance[head] = dict(question[arg], head=stored[head]['head'])
        for j, row in enumerate(stored):
            if row.get('head') == head:
                instance[j] = dict(instance[j], head=None)
    if variable_subject:
        form = dict(stored[pred]['morphology'])
        form.update({key: question[root]['morphology'].get(key) for key in ('number', 'gender', 'person')})
        instance[pred] = dict(stored[pred], morphology=form)
    if frame.marker is not None and stored[frame.share]['head'] == frame.marker:
        if stored[frame.marker]['head'] != pred:
            return None
        instance[frame.marker] = dict(stored[frame.marker], head=None)
        instance[frame.share] = dict(stored[frame.share], head=pred, role='object', case='accs')
    return instance


def _share_answer(question, root, focus, stored, frame):
    head = frame.share
    share = stored[head]
    amounts = [i for i, row in enumerate(stored) if row['role'] == 'numeral' and row['head'] == head]
    if len(amounts) > 1:
        return None
    amount = stored[amounts[0]] if amounts else None
    query = question[focus]
    if query.get('quantity_kind') != 'query' or query.get('quantity_modifier') not in (None, 'exact'):
        return None
    if query['role'] == 'numeral':
        target = query['head']
        if question[target]['lemma'] != share['lemma'] or question[target]['role'] != share['role']:
            return None
    elif query['role'] == share['role'] and query['head'] == root:
        from .distribution_questions import measure_unit

        if not measure_unit(question[root]['lemma'], share['lemma']):
            return None
        target = focus
    else:
        return None
    if any(j != focus and row.get('head') == target for j, row in enumerate(question)):
        return None
    children = [i for i, row in enumerate(stored) if row.get('head') == head]
    if any(j not in amounts for j in children):
        return None
    if amount is None:
        if (share.get('morphology') or {}).get('number') != 'sing':
            return None
        value = '1'
    else:
        if amount.get('quantity_kind') not in ('cardinal', 'fraction', 'range', 'collective', 'both'):
            return None
        value = amount.get('quantity')
        if not value or amount.get('quantity_modifier') not in (None, 'exact'):
            return None
    desired = [dict(row) for row in question]
    desired[target] = dict(share, head=root)
    if amount is not None:
        qnum = dict(amount, head=target)
        if focus == target:
            desired.append(qnum)
        else:
            desired[focus] = qnum
    elif focus != target:
        desired[focus] = dict(query, head=None)
    unit = share['surface']
    if target == focus and value.isdecimal():
        from .rules import dictionary

        forms = {inflected.word for parse in dictionary().parse(share['surface'])
                 if parse.normal_form == share['lemma'] and parse.tag.POS == 'NOUN'
                 and (base := parse.inflect({'nomn', 'sing'}))
                 and (inflected := base.make_agree_with_number(int(value)))}
        if len(forms) == 1:
            unit, = forms
    answer = value if target != focus else f'{value} {unit}'
    identity = ((amount.get('quantity_kind') if amount else 'cardinal', value, 'exact'),)
    if target == focus:
        identity = (share['lemma'], identity)
    return desired, identity, answer


def answers(core, question, focus, participants, budget):
    from .memory import _extraction, _participants, _query_rows, _root

    root = _root(question)
    for group, raw, frame, slots in _candidates(core, question, root):
        if not all(slots) or prod(map(len, slots)) > budget:
            continue
        for args in product(*slots):
            if len(set(args)) != len(args):
                continue
            stored = _instance(question, root, raw, frame, args)
            if stored is None:
                continue
            desired = question
            identity = answer = 'Да.'
            if focus is not None:
                if frame.share is None:
                    continue
                match = _share_answer(question, root, focus, stored, frame)
                if not match:
                    continue
                desired, identity, answer = match
            elif frame.share is not None:
                head = frame.share
                share = stored[head]
                targets = [i for i, row in enumerate(question) if row['head'] == root and row['role'] == share['role']
                           and row['lemma'] == share['lemma']]
                if len(targets) == 1:
                    qhead, = targets
                    target = question[qhead]
                    number = (share.get('morphology') or {}).get('number')
                    if number == (target.get('morphology') or {}).get('number'):
                        stored[head] = dict(share, surface=target['surface'])
                    if (number == 'sing' and frame.marker is not None and raw[frame.marker]['lemma'] == 'по'
                            and not any(row['role'] == 'numeral' and row['head'] == head for row in stored)):
                        for row in question:
                            if (row['role'] == 'numeral' and row['head'] == qhead and row.get('quantity') == '1'
                                    and row.get('quantity_kind') == 'cardinal' and not row.get('quantity_modifier')):
                                stored.append(dict(row, head=head))
            stored = _query_rows(stored, _participants(group.meta.get('source')), budget)
            if stored is None:
                continue
            if desired is not question:
                desired = _query_rows(desired, participants, budget)
                if desired is None:
                    continue
            if (desired[root].get('implicit_subject') == stored[frame.predicate].get('implicit_subject') == 'unresolved'
                    and not any(row['role'] == 'subject' and row['head'] == root for row in desired)
                    and (desired[root].get('morphology') or {}).get('number') == 'plur'):
                desired = list(desired)
                desired[root] = dict(desired[root], implicit_subject=None)
                stored[frame.predicate] = dict(stored[frame.predicate], implicit_subject=None)
            matched = _extraction(desired, stored, frame.predicate, group.meta['verbatim'], None, budget)
            if matched:
                support = tuple(dict.fromkeys((group.uid, *(ref for slot, arg in zip(slots, args) for ref in slot[arg]))))
                yield identity, answer, group.uid, support
