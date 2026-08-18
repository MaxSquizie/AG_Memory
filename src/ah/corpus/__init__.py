from .ahm import import_ahm_file, parse_ahm_text
from .errors import CorpusError
from .loader import (
    ColdCorpusWriter,
    CorpusImportResult,
    import_json_file,
    import_json_payload,
    max_excitation,
)
from .memory_import import (
    DIALOGUE_FORMAT,
    DialogueTurn,
    MemoryImportResult,
    dump_dialogue_payload,
    import_dialogue_cold,
    import_memory_snapshot,
    import_raw_experience,
    load_dialogue_file,
    parse_dialogue_json,
    split_raw_experience_text,
)

__all__ = [
    "ColdCorpusWriter",
    "CorpusError",
    "CorpusImportResult",
    "DIALOGUE_FORMAT",
    "DialogueTurn",
    "MemoryImportResult",
    "dump_dialogue_payload",
    "import_ahm_file",
    "import_corpus_file",
    "import_dialogue_cold",
    "import_json_file",
    "import_json_payload",
    "import_memory_snapshot",
    "import_raw_experience",
    "load_dialogue_file",
    "max_excitation",
    "parse_ahm_text",
    "parse_dialogue_json",
    "split_raw_experience_text",
]


def import_corpus_file(core, path, *, default_domain=None):
    from pathlib import Path

    from ah.model import Domain

    source = Path(path)
    domain = default_domain or Domain.C
    suffix = source.suffix.lower()
    if suffix == ".json":
        return import_json_file(core, source, default_domain=domain)
    if suffix in {".ahm", ".prj"}:
        return import_ahm_file(core, source, default_domain=domain)
    raise CorpusError(
        f"Unsupported corpus format {source.suffix or source.name!r}; "
        "use .json, .ahm, or .prj"
    )
