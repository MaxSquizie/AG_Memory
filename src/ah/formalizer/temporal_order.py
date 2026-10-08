"""Guaranteed ordering of closed temporal anchors; no event-time guessing."""
from ah.model import TimeLiteral


def compare_anchors(operator,first:TimeLiteral,second:TimeLiteral):
    alo,ahi=first.bounds[0],first.bounds[-1]
    blo,bhi=second.bounds[0],second.bounds[-1]
    if operator=='AFTER':
        return compare_anchors('BEFORE',second,first)
    if operator=='BEFORE':
        if ahi<blo: return True
        if alo>=bhi: return False
        return None
    if operator=='DURING':
        return blo<=alo and ahi<=bhi
    raise ValueError('REGISTRY_REJECT')
