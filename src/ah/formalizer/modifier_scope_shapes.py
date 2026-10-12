"""Bounded scope trees: lexical nesting and conjunction over one shared event."""
from itertools import product


def partitions(items):
    if not items:
        yield (); return
    first, *tail = items
    for rest in partitions(tuple(tail)):
        yield ((first,), *rest)
        for i, block in enumerate(rest):
            yield (*rest[:i], (first, *block), *rest[i+1:])


def shapes(count, limit):
    """Each modifier occurs once; every branch terminates at the SAME base.

    AND child order is canonical; lexical nesting is never commuted. Overflow
    rejects the whole inventory, not just its unexplored suffix.
    """
    cache = {}
    def scopes(items):
        if not items: return [None]
        if items in cache: return cache[items]
        result = []
        for blocks in partitions(items):
            branches = []
            for block in blocks:
                options = []
                for outer in block:
                    for inner in scopes(tuple(i for i in block if i != outer)):
                        options.append(('MOD', outer, inner))
                branches.append(options)
            for combo in product(*branches):
                result.append(combo[0] if len(combo) == 1 else ('AND', combo))
                if len(result) > limit: raise OverflowError
        cache[items] = result
        return result
    return scopes(tuple(range(count)))


def tree(frame):
    return frame.semantic.get('component_scope_tree', {'frame_ref': frame.frame_id})


def argument(frame, attitude):
    return ({'tree': tree(frame)} if 'component_scope_tree' in frame.semantic
            else {'frame_ref': frame.frame_id}) | {'attitude': attitude}


def label(shape, event, units):
    if shape is None: return 'SAME event «'+event+'»'
    if shape[0] == 'AND':
        return 'BOTH('+ '; '.join(label(s,event,units) for s in shape[1])+')'
    unit=units[shape[1]]
    surface=' '.join([unit['token'].span,*[a.span for a,v in unit['adjectives']],
                      *[e.span for e,v in unit['entities']]])
    return '«'+surface+'» scopes over ('+label(shape[2],event,units)+')'
