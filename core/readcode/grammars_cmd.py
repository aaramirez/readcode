"""``readcode grammars``: list / pre-download the tree-sitter grammars the indexer uses."""

from __future__ import annotations

from readcode.indexer import NOT_INDEXED, PACK_NAMES
from readcode.snapshot import LANGUAGES


class GrammarsError(RuntimeError):
    pass


def used_grammars() -> list[str]:
    """Pack grammar names the indexer can load, sorted."""
    return sorted({PACK_NAMES.get(lang, lang) for lang in LANGUAGES.values() if lang not in NOT_INDEXED})


def cached_grammars() -> set[str]:
    """Grammars already in the local cache (loadable without network)."""
    import tree_sitter_language_pack as tslp

    return set(tslp.downloaded_languages())


def grammar_status(names: list[str] | None = None) -> list[tuple[str, bool]]:
    """(grammar, cached) for ``names`` (default: all used by the indexer)."""
    used = used_grammars()
    wanted = names or used
    unknown = [n for n in wanted if n not in used]
    if unknown:
        raise GrammarsError(f"gramática desconocida: {', '.join(unknown)} (disponibles: {', '.join(used)})")
    cached = cached_grammars()
    return [(n, n in cached) for n in wanted]


def fetch_grammars(names: list[str] | None = None) -> list[str]:
    """Download the requested grammars (all if none given); returns those now cached.

    Raises GrammarsError when the download fails (e.g. no network).
    """
    import tree_sitter_language_pack as tslp

    wanted = [n for n, _ in grammar_status(names)]
    try:
        tslp.download(wanted)
    except Exception as exc:
        raise GrammarsError(f"no se pudieron descargar las gramáticas ({type(exc).__name__}: {exc})") from exc
    missing = [n for n in wanted if n not in cached_grammars()]
    if missing:
        raise GrammarsError(f"no se descargaron: {', '.join(missing)}")
    return wanted
