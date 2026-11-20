from .parser import AnalysisBudgetExceeded, Link
from .spatial_clauses import bind
from .spatial_leaves import trees as leaves
from .spatial_prefix import deictic_role, relative_role
from .utterances import _map, _root


def trees(tokens, local, budget, chart, splits):
    if not tokens or not relative_role(tokens[0].surface):
        return
    marker = tokens[0]
    examined = 0
    anchors = tuple(i for i, token in enumerate(tokens) if deictic_role(token.surface)
                    and chart.permits(marker.start, token.start))
    if not anchors:
        return
    for end, start in splits:
        if start > anchors[-1]:
            break
        for matrix in leaves(tokens[start:], local, budget):
            root = _root(matrix)
            hosts = tuple(i for i in anchors if i >= start and matrix[i - start].role == 'adverb'
                          and matrix[i - start].head == root)
            if not hosts:
                continue
            outer = _map(matrix, range(start, len(tokens)))
            for inner in leaves(tokens[1:end], local, budget):
                child = 1 + _root(inner)
                links = outer | _map(inner, range(1, end))
                links[0] = Link('adverb', marker.surface.casefold(), child, 'B1')
                if end < start:
                    links[end] = Link('punctuation', ',', child, 'CL.PUNCT')
                tree = tuple(links[i] for i in range(len(tokens)))
                for host in hosts:
                    examined += 1
                    if examined > budget:
                        raise AnalysisBudgetExceeded('SPATIAL_CLAUSE_BUDGET')
                    yield bind(tree, 0, child, host, 'clause_relative')
