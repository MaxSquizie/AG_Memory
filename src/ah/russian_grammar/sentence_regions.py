from . import (
    attributive_series, calendar_regions, clause_series, dated_name_notes, finite_insertions, framed_clauses,
    infinitive_elaborations, lexical_parts, measured_series, mixed_predications, named_arguments, named_regions,
    named_series, nominal_definitions, nominal_designations, nominal_dimensions, nominal_mentions, nominal_parentheticals, nominal_predicates,
    participial_regions, predicate_lists, predicative_groups, quote_titles, reference_directives, temporal_groups,
)


def _primary_regions(tokens, parse, budget):
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
    yield from named_regions.matrix_readings(tokens, parse, budget)


def trees(tokens, parse, budget, *, dated_members=None):
    found = False
    for tree in _primary_regions(tokens, parse, budget):
        found = True
        yield tree
    if not found and dated_members is not None:
        for tree in dated_members(tokens):
            found = True
            yield tree
        if found:
            return
    yield from temporal_groups.trees(tokens, parse, budget)
    yield from reference_directives.trees(tokens, parse, budget)
    yield from quote_titles.trees(tokens, parse, budget)
    yield from nominal_predicates.trees(tokens, budget=budget)
    yield from participial_regions.trees(tokens, budget=budget)
    yield from predicative_groups.trees(tokens, parse, budget)


def _relative_child_readings(part, parse, budget):
    yield from parse(part)
    yield from trees(part, parse, budget)


def remaining(tokens, parse, budget, *, text, selected):
    from . import marked_regions
    from .utterances import nominal_then_finite
    from .contrastive_regions import nominal_remnants
    from .relative_clauses import final_subject_relative

    yield from marked_regions.nominal_relative(tokens, text, selected,
        lambda part: named_regions.matrix_readings(part, parse, budget),
        lambda part: _relative_child_readings(part, parse, budget), budget)
    from . import generalizing_series
    yield from generalizing_series.trees(tokens, parse, budget)
    yield from quote_titles.quoted_arguments(tokens, parse, budget)
    from . import homogeneous
    from .utterances import _parataxis

    def expanded(part):
        yield from homogeneous.expanded_infinitives(part, parse, budget)
        yield from named_series.initial_name_groups(part, parse, budget)

    yield from expanded(tokens)
    if any(t.surface in (':', ';') for t in tokens):
        def leaf(part):
            yield from parse(part)
            yield from expanded(part)
        yield from _parataxis(tokens, leaf, explicit=True)
    yield from nominal_then_finite(tokens, parse)
    yield from nominal_remnants(tokens, parse, budget)
    yield from final_subject_relative(tokens, parse, budget)
    yield from named_arguments.clauses_with_named_series(tokens, parse, budget)
    yield from named_arguments.missing_subjects(tokens, parse)
    yield from clause_series.trees(tokens, parse, budget)
    yield from nominal_mentions.trees(tokens, parse, budget)
    yield from participial_regions.trees(tokens, budget=budget, extended=True)


def confirmation(tokens, tree, i, text):
    from . import generalizing_series
    grammars = (
        generalizing_series,
        calendar_regions, mixed_predications, measured_series, dated_name_notes, infinitive_elaborations, predicate_lists,
        attributive_series, quote_titles, reference_directives, nominal_mentions, temporal_groups,
        clause_series, nominal_parentheticals, named_regions, lexical_parts, framed_clauses, named_series, named_arguments, nominal_dimensions,
    )
    for grammar in grammars:
        probe = grammar.confirmation(tokens, tree, i, text)
        if probe is not None:
            return probe
    return None

def additional_readings(tokens, parse, budget):
    from .utterances import missing_boundaries

    yield from missing_boundaries(tokens, parse, lambda part: _relative_child_readings(part, parse, budget), budget)
    yield from additional_nominal_readings(tokens, parse, budget)


def additional_nominal_readings(tokens, parse, budget):
    from itertools import chain

    def expanded(part):
        return chain(parse(part), named_regions.unlisted_genitives(part, parse, budget))

    yield from named_regions.unlisted_genitives(tokens, parse, budget)
    yield from calendar_regions.leading_year_range(tokens, expanded)
