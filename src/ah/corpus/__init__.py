from .ahm import import_ahm_file, parse_ahm_text
from .errors import CorpusError
from .loader import (
    ColdCorpusWriter,
    CorpusImportResult,
    import_json_file,
    import_json_payload,
    max_excitation,
)

__all__ = [
    "ColdCorpusWriter",
    "CorpusError",
    "CorpusImportResult",
    "import_ahm_file",
    "import_corpus_file",
    "import_json_file",
    "import_json_payload",
    "max_excitation",
    "parse_ahm_text",
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
