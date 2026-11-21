from functools import cache
from importlib.resources import files

from .case_arguments import _lexicon as bare_government, dative_recipients
from .infinitives import FRAMES
from .morphology import CASE_EQUIVALENTS, PREDICATE_ROLES
from .prepositions import GOVERNMENT
from .rules import fixed_noun_cases, known_forms


@cache
def _required():
    resource = files(__package__).joinpath('lexicon/required_arguments.tsv')
    groups = {}
    for row in resource.read_text(encoding='utf-8').splitlines():
        lemma, pos, roles = row.split('\t')
        groups.setdefault((lemma, pos), []).append(frozenset(roles.split()))
    return groups


def violation(tokens, tree):
    from .ellipsis import unsupported_count
    from .partitive_domains import cardinality_violation

    if reason := cardinality_violation(tree):
        return reason
    children = [set() for _ in tree]
    for link in tree:
        if link.head is not None:
            children[link.head].add(link.role)
            if tree[link.head].rule == 'GAP' and (link.role == 'object' or link.rule in ('V.GOV', 'GAP.NOUN')):
                children[link.head].add('parallel_argument')
    for i, link in enumerate(tree):
        if link.role != 'governed' or link.case != 'accs' or 'numeral' not in children[i]:
            continue
        prep = tree[link.head] if link.head is not None else None
        if prep is None or prep.role != 'preposition' or prep.lemma != 'по' or prep.head is None:
            continue
        governor = tree[prep.head]
        if governor.morphology and governor.morphology.transitivity == 'tran':
            children[prep.head].add('object')
    for i, (token, link) in enumerate(zip(tokens, tree)):
        form = link.morphology
        if unsupported_count(tree, i):
            return 'UNSUPPORTED_QUANTITY_ELLIPSIS'
        if link.lemma == 'себя' and link.antecedent is None:
            return 'UNBOUND_REFLEXIVE'
        if link.rule == 'V.GOV' or link.rule == 'GAP.NOUN' and link.role != 'object':
            if link.head is None:
                return 'INVALID_GOVERNOR'
            governor = tree[link.head].lemma
            cases, roles = bare_government()
            frame = FRAMES.get(governor)
            controlled = (link.role == 'recipient' and 'infinitive' in children[link.head]
                          and frame and link.case in frame.recipient_cases)
            attested = roles.get((governor, link.case), 'oblique')
            if (link.role == 'recipient' and link.case == 'datv' and governor in dative_recipients()
                    and 'datv' in cases.get(governor, ()) and 'object' in children[link.head]):
                controlled = True
            if not controlled and (link.case not in cases.get(governor, ()) or
                                   link.role not in (attested, 'oblique')):
                return 'INVALID_GOVERNED_ROLE'
        if link.role == 'governed':
            if link.head is None or tree[link.head].role != 'preposition':
                return 'INVALID_GOVERNOR'
            allowed = GOVERNMENT.get(tree[link.head].lemma)
            if not allowed:
                return 'UNKNOWN_GOVERNMENT'
            if link.case not in allowed and CASE_EQUIVALENTS.get(link.case) not in allowed:
                if link.case is not None or len(fixed_noun_cases(token.surface, link.lemma, allowed)) < 2:
                    return 'INVALID_GOVERNED_CASE'
        if link.rule == 'V.CMP' and (not form or form.pos != 'COMP'):
            return 'INVALID_COMPARATIVE_PREDICATE'
        if link.rule == 'CMP.ATTR':
            from .nominal_definitions import comparative_forms
            if not any(lemma == link.lemma for lemma, _ in comparative_forms(token.surface)):
                return 'INVALID_COMPARATIVE_ATTRIBUTE'
        if link.role == 'comparison_standard':
            marked = 'comparison_marker' in children[i]
            if (link.head is None or tree[link.head].rule not in ('V.CMP', 'CMP.ADV', 'CMP.ATTR') or
                    link.case != ('nomn' if marked else 'gent')):
                return 'INVALID_COMPARISON'
        if link.role not in PREDICATE_ROLES | {'infinitive', 'converb', 'participle'}:
            continue
        if link.rule == 'V2':
            surface = link.recovery.corrected if link.recovery else token.surface
            cases = {'nomn', 'ablt'} if 'copula' in children[i] else {'nomn'}
            readings = (tag for lemma, tag in known_forms(surface) if lemma == link.lemma
                        and (not form or not form.pos or tag.POS == form.pos)
                        and (not form or not form.case or tag.case == form.case))
            if not any(tag.POS in ('NOUN', 'ADJF', 'ADJS', 'PRTS') and tag.case in cases | {None}
                       for tag in readings):
                return 'INVALID_NOMINAL_PREDICATE'
        if form and form.transitivity == 'intr' and 'object' in children[i]:
            return 'INTRANSITIVE_OBJECT'
        roles = children[i]
        if link.shared_object is not None:
            roles = roles | {'object'}
        requirements = (*_required().get((link.rule, '*'), ()),
                        *_required().get((link.lemma, form.pos if form else None), ()))
        for alternatives in requirements:
            if not roles.intersection(alternatives):
                return 'MISSING_REQUIRED_ARGUMENT'
    return None
