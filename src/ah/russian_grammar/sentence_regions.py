from . import (
    attributive_series, calendar_regions, clause_series, dated_name_notes, finite_insertions, framed_clauses,
    infinitive_elaborations, lexical_parts, measured_series, mixed_predications, named_arguments, named_regions,
    named_series, nominal_definitions, nominal_designations, nominal_dimensions, nominal_mentions, nominal_parentheticals, nominal_predicates,
    participial_regions, predicate_lists, predicative_groups, quote_titles, reference_directives, temporal_groups,
)


def trees(tokens, parse, budget):
    yield from infinitive_elaborations.trees(tokens, parse, budget)
    yield from predicate_lists.trees(tokens, parse, budget)
    mixed = tuple(mixed_predications.trees(tokens, parse, budget))
    yield from mixed
    yield from measured_series.trees(tokens, parse, budget)
    yield from attributive_series.trees(tokens, parse, budget)
    yield from calendar_regions.trees(tokens, parse, budget)
    yield from finite_insertions.trees(tokens, parse, budget)
    yield from named_series.trees(tokens, parse, budget)
    yield from nominal_dimensions.trees(tokens, parse, budget)
    supplied = mixed if mixed_predications.parallel(mixed) else ()
    yield from nominal_designations.trees(tokens, parse, budget, complete=supplied)
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
    from .utterances import nominal_then_finite

    yield from nominal_then_finite(tokens, parse)
    yield from named_arguments.missing_subjects(tokens, parse)
    yield from clause_series.trees(tokens, parse, budget)
    yield from nominal_mentions.trees(tokens, parse, budget)
    yield from participial_regions.trees(tokens, budget=budget, extended=True)


def confirmation(tokens, tree, i, text):
    grammars = (
        calendar_regions, mixed_predications, measured_series, dated_name_notes, infinitive_elaborations, predicate_lists,
        attributive_series, quote_titles, reference_directives, nominal_mentions, temporal_groups,
        clause_series, nominal_parentheticals, named_regions, lexical_parts, framed_clauses, named_series, named_arguments, nominal_dimensions,
    )
    for grammar in grammars:
        probe = grammar.confirmation(tokens, tree, i, text)
        if probe is not None:
            return probe
    return None
