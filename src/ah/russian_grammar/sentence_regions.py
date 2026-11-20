from . import nominal_predicates, participial_regions, predicative_groups, quote_titles, reference_directives


def trees(tokens, parse, budget):
    yield from reference_directives.trees(tokens, parse, budget)
    yield from quote_titles.trees(tokens, parse, budget)
    yield from nominal_predicates.trees(tokens, budget=budget)
    yield from participial_regions.trees(tokens, budget=budget)
    yield from predicative_groups.trees(tokens, parse, budget)


def remaining(tokens, budget):
    yield from participial_regions.trees(tokens, budget=budget, extended=True)


def confirmation(tokens, tree, i, text):
    return quote_titles.confirmation(tokens, tree, i, text) or reference_directives.confirmation(tokens, tree, i, text)
