"""Lower an explicitly selected three-part conditional to the existing algebra."""
from copy import deepcopy


def branch_tree(operands, anchors=()):
    if len(operands) != 3:
        raise ValueError('CONDITIONAL_BRANCHES_UNCLOSED')
    condition, positive, negative = operands
    # The negation scopes over the complete selected condition. A nested
    # negative/content clause is never extracted as the else condition.
    return {'operator': 'AND', 'anchor_refs': list(anchors), 'operands': [
        {'operator': 'IMPLIES', 'operands': [deepcopy(condition), deepcopy(positive)]},
        {'operator': 'IMPLIES', 'operands': [
            {'operator': 'NOT', 'operands': [deepcopy(condition)]}, deepcopy(negative)]},
    ]}
