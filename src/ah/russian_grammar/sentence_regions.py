from . import (
    clause_series, finite_insertions, framed_clauses, lexical_parts, named_arguments, named_regions,
    named_series, nominal_definitions, nominal_designations, nominal_dimensions, nominal_mentions, nominal_predicates,
    participial_regions, predicative_groups, quote_titles, reference_directives, temporal_groups,
)


def trees(tokens, parse, budget):
    yield from finite_insertions.trees(tokens, parse, budget)
    yield from named_series.trees(tokens, parse, budget)
    yield from nominal_dimensions.trees(tokens, parse, budget)
    yield from nominal_designations.trees(tokens, parse, budget)
    yield from framed_clauses.trees(tokens, parse, budget)
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
    grammars = (quote_titles, reference_directives, nominal_mentions, temporal_groups, clause_series,
                named_regions, lexical_parts, framed_clauses, named_series, named_arguments, nominal_dimensions)
    for grammar in grammars:
        probe = grammar.confirmation(tokens, tree, i, text)
        if probe is not None:
            return probe
    return None
