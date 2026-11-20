from . import (
    clause_series, named_regions, nominal_definitions, nominal_mentions, nominal_predicates,
    participial_regions, predicative_groups, quote_titles, reference_directives, temporal_groups,
)


def trees(tokens, parse, budget):
    yield from nominal_definitions.trees(tokens, parse, budget)
    yield from named_regions.trees(tokens, parse, budget)
    yield from temporal_groups.trees(tokens, parse, budget)
    yield from reference_directives.trees(tokens, parse, budget)
    yield from quote_titles.trees(tokens, parse, budget)
    yield from nominal_predicates.trees(tokens, budget=budget)
    yield from participial_regions.trees(tokens, budget=budget)
    yield from predicative_groups.trees(tokens, parse, budget)


def remaining(tokens, parse, budget):
    yield from clause_series.trees(tokens, parse, budget)
    yield from nominal_mentions.trees(tokens, parse, budget)
    yield from participial_regions.trees(tokens, budget=budget, extended=True)


def confirmation(tokens, tree, i, text):
    for grammar in (quote_titles, reference_directives, nominal_mentions, temporal_groups, clause_series, named_regions):
        probe = grammar.confirmation(tokens, tree, i, text)
        if probe is not None:
            return probe
    return None
