def indexed_candidates(analyzer, word, *, max_distance, limit):
    query = word.casefold()
    if not query or max_distance < 0 or limit <= 0:
        return ()
    words = analyzer.dictionary.words
    dictionary = getattr(words, "dct", None)
    alphabet = "абвгдеёжзийклмнопрстуфхцчшщъыьэюя-"
    initial_row = tuple(range(len(query) + 1))
    found: set[str] = set()

    def visit(prefix: str, state: int, previous_row: tuple[int, ...]) -> None:
        if len(found) >= limit:
            return
        for char in alphabet:
            candidate = prefix + char
            if dictionary is None:
                next_state = 0 if next(iter(words.iterkeys(candidate)), None) is not None else None
            else:
                next_state = dictionary.follow_bytes(char.encode("utf-8"), state)
            if next_state is None:
                continue
            current = [previous_row[0] + 1]
            for column, query_char in enumerate(query, start=1):
                current.append(
                    min(
                        current[column - 1] + 1,
                        previous_row[column] + 1,
                        previous_row[column - 1] + (query_char != char),
                    )
                )
            if current[-1] <= max_distance and candidate in words:
                found.add(candidate)
                if len(found) >= limit:
                    return
            if min(current) <= max_distance:
                visit(candidate, next_state, tuple(current))

    visit("", dictionary.ROOT if dictionary is not None else 0, initial_row)

    if max_distance >= 1:
        chars = list(query)
        for index in range(len(chars) - 1):
            if chars[index] == chars[index + 1]:
                continue
            swapped = chars.copy()
            swapped[index], swapped[index + 1] = swapped[index + 1], swapped[index]
            candidate = "".join(swapped)
            if analyzer.word_is_known(candidate):
                found.add(candidate)

    return tuple(sorted(found))
