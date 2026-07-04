import unittest

from extractor import AnimeExtractor, parse_command_options
from extractors.base import SUPPORTED_SOURCES, _split_source_id


def fake_source(name, calls, results=False, supports_dub=False):
    class Extractor:
        site_name = name
        _VALID_URL = r"$^"

        def search(self, title, dub=False):
            calls.append(f"{name}-search")
            if not results:
                return []
            return [{
                "id": f"{name}:https://example.invalid/{name}/{title}",
                "title": title,
                "total_episodes": 12,
                "extractor": name,
            }]

        def list_episodes(self, title_or_id, dub=False):
            return ["1"]

        def get_episode(self, title_or_id, episode, dub=False):
            calls.append(name)
            if not results:
                raise RuntimeError("offline")
            return {
                "url": f"https://media.invalid/{name}/{episode}.m3u8",
                "referer": f"https://example.invalid/{name}/",
                "extractor": name,
            }

    Extractor.supports_dub = supports_dub
    return Extractor


class TestSourceIds(unittest.TestCase):
    def test_all_supported_prefixes_are_split(self):
        self.assertEqual(
            set(SUPPORTED_SOURCES),
            {
                "jkanime", "animeflv", "animeav1", "tioanime",
                "animefenix", "monoschino", "gogoanime",
            },
        )
        for source in SUPPORTED_SOURCES:
            self.assertEqual(
                _split_source_id(f"{source}:https://example.invalid/a"),
                (source, "https://example.invalid/a"),
            )


class TestLanguageFallback(unittest.TestCase):
    def test_spanish_sub_order(self):
        calls = []
        classes = tuple(
            fake_source(name, calls, results=name == "animeav1")
            for name in (
                "animeav1", "tioanime", "animefenix", "animeflv", "jkanime"
            )
        )
        results = AnimeExtractor(classes).search("Frieren", lang="es")
        self.assertEqual(
            calls,
            [
                "jkanime-search", "animeflv-search", "animefenix-search",
                "tioanime-search", "animeav1-search",
            ],
        )
        self.assertEqual(results[0]["extractor"], "animeav1")

    def test_spanish_dub_starts_with_monoschino_and_skips_sub_sources(self):
        calls = []
        classes = (
            fake_source("jkanime", calls),
            fake_source("animefenix", calls),
            fake_source("monoschino", calls, supports_dub=True),
            fake_source("animeflv", calls, results=True, supports_dub=True),
            fake_source("animeav1", calls, results=True, supports_dub=True),
        )
        results = AnimeExtractor(classes).search("Dragon Ball", dub=True)
        self.assertEqual(calls, ["monoschino-search", "animeflv-search"])
        self.assertEqual(results[0]["extractor"], "animeflv")

    def test_english_uses_only_gogoanime(self):
        calls = []
        classes = (
            fake_source("jkanime", calls, results=True),
            fake_source("gogoanime", calls, results=True),
        )
        results = AnimeExtractor(classes).search("Solo Leveling", lang="en")
        self.assertEqual(calls, ["gogoanime-search"])
        self.assertEqual(results[0]["extractor"], "gogoanime")

    def test_episode_falls_through_animeflv_to_animefenix(self):
        calls = []
        classes = (
            fake_source("jkanime", calls),
            fake_source("animeflv", calls),
            fake_source("animefenix", calls, results=True),
        )
        result = AnimeExtractor(classes).get_episode(
            "jkanime:https://jkanime.net/frieren/", "1", title="Frieren"
        )
        self.assertEqual(
            calls,
            ["jkanime", "animeflv-search", "animefenix-search", "animefenix"],
        )
        self.assertEqual(result["extractor"], "animefenix")

    def test_dub_episode_falls_from_monoschino_to_animeflv(self):
        calls = []
        classes = (
            fake_source("monoschino", calls, supports_dub=True),
            fake_source("animeflv", calls, results=True, supports_dub=True),
        )
        result = AnimeExtractor(classes).get_episode(
            "monoschino:https://monoschino2.com/anime/dragon-ball/",
            "1",
            dub=True,
            title="Dragon Ball",
        )
        self.assertEqual(
            calls, ["monoschino", "animeflv-search", "animeflv"]
        )
        self.assertEqual(result["extractor"], "animeflv")

    def test_cli_options_default_to_spanish(self):
        self.assertEqual(
            parse_command_options(["--dub", "Dragon", "Ball"]),
            ("es", True, ["Dragon", "Ball"]),
        )
        self.assertEqual(
            parse_command_options(["--lang", "en", "Solo Leveling"]),
            ("en", False, ["Solo Leveling"]),
        )


if __name__ == "__main__":
    unittest.main()
