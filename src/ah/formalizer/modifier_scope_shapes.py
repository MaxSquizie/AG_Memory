"""Rendering of selected modifier topology; enumeration lives nowhere here."""


def tree(frame):
    from .composition_tree import expression
    return expression(frame)


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
