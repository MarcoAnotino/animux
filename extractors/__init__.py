import re
import urllib.parse

from .animeav1 import AnimeAV1Extractor
from .animefenix import AnimeFenixExtractor
from .animeflv import AnimeFLVExtractor
from .base import _split_source_id
from .gogoanime import GogoanimeExtractor
from .jkanime import JkanimeExtractor
from .monoschino import MonoschinoExtractor
from .tioanime import TioAnimeExtractor


SOURCE_ORDER = {
    ("es", False): (
        "jkanime", "animeflv", "animefenix", "tioanime", "animeav1"
    ),
    ("es", True): ("monoschino", "animeflv", "animeav1"),
    ("en", False): ("gogoanime",),
    ("en", True): ("gogoanime",),
}


EXTRACTOR_CLASSES = (
    JkanimeExtractor,
    AnimeFLVExtractor,
    AnimeFenixExtractor,
    TioAnimeExtractor,
    AnimeAV1Extractor,
    MonoschinoExtractor,
    GogoanimeExtractor,
)


class AnimeExtractor:
    """Search language-specific sources and resolve streams with fallback."""

    extractor_classes = EXTRACTOR_CLASSES

    def __init__(self, extractor_classes=None):
        classes = (
            self.extractor_classes
            if extractor_classes is None
            else extractor_classes
        )
        self._extractors = [extractor_class() for extractor_class in classes]

    def extract(self, url):
        for extractor in self._extractors:
            match = re.match(extractor._VALID_URL, url)
            if match:
                return extractor.extract(url, match)
        raise ValueError(f"Ningún extractor interno soporta la URL: {url}")

    def _ordered_extractors(self, lang="es", dub=False, preferred_source=None):
        if lang not in {"es", "en"}:
            raise ValueError(f"Idioma no soportado: {lang}")
        extractors_by_source = {
            extractor.site_name: extractor
            for extractor in self._extractors
        }
        source_order = list(SOURCE_ORDER[(lang, bool(dub))])
        if preferred_source in extractors_by_source:
            source_order.insert(0, preferred_source)
        seen = set()
        ordered = []
        for source in source_order:
            if source in seen or source not in extractors_by_source:
                continue
            seen.add(source)
            ordered.append(extractors_by_source[source])
        return [
            extractor
            for extractor in ordered
            if not dub or getattr(extractor, "supports_dub", False)
        ]

    @staticmethod
    def _fallback_title(identifier):
        value = urllib.parse.unquote(str(identifier or "").rstrip("/"))
        value = value.rsplit("/", 1)[-1]
        return value.replace("-", " ").replace("_", " ")

    @staticmethod
    def _record_error(extractor, action, exc, errors=None):
        message = f"{extractor.site_name}: {exc}"
        if errors is not None:
            errors.append(message)
        log = getattr(extractor, "_log", None)
        if callable(log):
            log(f"[{extractor.site_name}][Aviso] {action} falló: {exc}")

    def search(self, title, dub=False, lang="es"):
        ordered = self._ordered_extractors(lang=lang, dub=dub)

        for extractor in ordered:
            try:
                results = extractor.search(title, dub=dub)
            except Exception as exc:
                self._record_error(extractor, "Búsqueda", exc)
                continue
            if results:
                return results
        return []

    def list_episodes(self, title_or_id, dub=False, lang="es"):
        source, identifier = _split_source_id(title_or_id)
        ordered = self._ordered_extractors(
            lang=lang, dub=dub, preferred_source=source
        )
        errors = []
        fallback_title = (
            self._fallback_title(identifier) if source else str(identifier)
        )

        if source and ordered and ordered[0].site_name == source:
            selected = ordered[0]
            try:
                episodes = selected.list_episodes(title_or_id, dub=dub)
                if episodes:
                    return episodes
            except Exception as exc:
                self._record_error(selected, "Listado de episodios", exc, errors)

        for extractor in ordered:
            if source and extractor.site_name == source:
                continue
            try:
                matches = extractor.search(fallback_title, dub=dub)
                if not matches:
                    raise RuntimeError("sin coincidencias")
                for result in matches:
                    episodes = extractor.list_episodes(result["id"], dub=dub)
                    if episodes:
                        return episodes
                raise RuntimeError("sin episodios")
            except Exception as exc:
                self._record_error(extractor, "Listado de episodios", exc, errors)

        if source and not any(item.site_name == source for item in ordered):
            errors.insert(0, f"{source}: no soporta este idioma o modo")

        raise RuntimeError(
            "No se pudo obtener la lista de episodios. " + "; ".join(errors)
        )

    def get_episode(
        self, title_or_id, episode, dub=False, title=None, lang="es"
    ):
        source, identifier = _split_source_id(title_or_id)
        ordered = self._ordered_extractors(
            lang=lang, dub=dub, preferred_source=source
        )
        errors = []

        if source:
            selected = next(
                (item for item in ordered if item.site_name == source), None
            )
            if selected:
                try:
                    return selected.get_episode(title_or_id, episode, dub=dub)
                except Exception as exc:
                    self._record_error(selected, "Episodio", exc, errors)

        fallback_title = title or (
            self._fallback_title(identifier) if source else identifier
        )

        for extractor in ordered:
            if source and extractor.site_name == source:
                continue
            try:
                matches = extractor.search(fallback_title, dub=dub)
                if not matches:
                    raise RuntimeError("sin coincidencias")
                return extractor.get_episode(
                    matches[0]["id"], episode, dub=dub
                )
            except Exception as exc:
                self._record_error(extractor, "Episodio", exc, errors)

        raise RuntimeError(
            "Ninguna fuente devolvió el episodio. " + "; ".join(errors)
        )


__all__ = [
    "AnimeExtractor",
    "JkanimeExtractor",
    "AnimeFLVExtractor",
    "AnimeAV1Extractor",
    "AnimeFenixExtractor",
    "TioAnimeExtractor",
    "MonoschinoExtractor",
    "GogoanimeExtractor",
    "EXTRACTOR_CLASSES",
    "SOURCE_ORDER",
]
