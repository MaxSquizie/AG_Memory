from .morphology import PREDICATE_ROLES


EVENT_ROLES = PREDICATE_ROLES | {'infinitive', 'converb', 'participle'}


def owners(tree, modifier):
    phrase = set()
    i = tree[modifier].head
    while i is not None and tree[i].role not in EVENT_ROLES:
        phrase.add(i)
        i = tree[i].head
    candidates = []
    while i is not None:
        event = tree[i]
        participants = [j for j, link in enumerate(tree) if link.head == i and link.role == 'subject']
        if event.controller is not None:
            participants.append(event.controller)
        accessible = [j for j in participants if j not in phrase]
        if not accessible:
            accessible = [j for j, link in enumerate(tree) if link.head == i and link.role == 'experiencer'
                          and j not in phrase]
        candidates.extend(accessible or (None,))
        if event.role != 'infinitive':
            break
        i = event.head
    return tuple(dict.fromkeys(candidates)) or (None,)
