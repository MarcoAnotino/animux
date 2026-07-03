import unittest
from unittest.mock import Mock

from extractor import (
    AnimeAV1Extractor,
    AnimeExtractor,
    AnimeFLVExtractor,
)


class TestAnimeFLVMetadata(unittest.TestCase):
    def setUp(self):
        self.extractor = AnimeFLVExtractor()

    def test_search_returns_real_episode_count(self):
        self.extractor._download_webpage = Mock(return_value="""
            <article><a href="/anime/sousou-no-frieren">
              <h3>Sousou no Frieren</h3>
            </a></article>
        """)
        self.extractor.list_episodes = Mock(return_value=["1", "2", "3"])

        results = self.extractor.search("frieren")

        self.assertEqual(results[0]["total_episodes"], 3)
        self.assertEqual(
            results[0]["id"],
            "animeflv:https://www3.animeflv.net/anime/sousou-no-frieren",
        )

    def test_dub_search_filters_subtitled_listing(self):
        self.extractor._download_webpage = Mock(return_value="""
            <article><a href="/anime/frieren"><h3>Frieren</h3></a></article>
            <article><a href="/anime/frieren-latino">
              <h3>Frieren (Doblaje Latino)</h3>
            </a></article>
        """)
        self.extractor.list_episodes = Mock(return_value=["1"])

        results = self.extractor.search("frieren", dub=True)

        self.assertEqual(len(results), 1)
        self.assertIn("Doblaje Latino", results[0]["title"])

    def test_reads_official_episode_array(self):
        self.extractor._download_webpage = Mock(
            return_value='var episodes = [[3, 0], [1, 0], [2, 0]];'
        )

        episodes = self.extractor.list_episodes(
            "animeflv:https://www3.animeflv.net/anime/frieren"
        )

        self.assertEqual(episodes, ["1", "2", "3"])


class TestAnimeAV1Metadata(unittest.TestCase):
    def test_reads_group_item_episode_cards(self):
        extractor = AnimeAV1Extractor()
        extractor._download_webpage = Mock(return_value="""
            <article class="group/item"><span>2</span></article>
            <article class="group/item"><span>1</span></article>
        """)

        episodes = extractor.list_episodes(
            "animeav1:https://animeav1.com/media/frieren"
        )

        self.assertEqual(episodes, ["1", "2"])

    def test_selects_dub_embed_block(self):
        extractor = AnimeAV1Extractor()
        page = (
            'embeds:{SUB:[{server:"HLS",url:"https://sub.example/e"}],'
            'DUB:[{server:"MP4Upload",url:"https://dub.example/e"}]}}'
        )

        urls = extractor._iframe_urls_from_page(
            page, "https://animeav1.com/media/frieren/1", dub=True
        )

        self.assertEqual(urls, ["https://dub.example/e"])


class TestSpanishFallback(unittest.TestCase):
    def test_search_preserves_source_priority(self):
        def source(name, dub=False):
            class Extractor:
                site_name = name
                supports_dub = dub
                _VALID_URL = r"$^"

                def search(self, title, dub=False):
                    return [{
                        "id": f"{name}:id",
                        "title": title,
                        "total_episodes": 12,
                        "extractor": name,
                    }]

            return Extractor

        orchestrator = AnimeExtractor((
            source("jkanime"),
            source("animeflv", dub=True),
            source("animeav1"),
        ))

        results = orchestrator.search("Frieren")

        self.assertEqual(
            [result["extractor"] for result in results],
            ["jkanime", "animeflv", "animeav1"],
        )

    def test_episode_falls_back_from_jkanime_to_animeflv(self):
        calls = []

        class Jkanime:
            site_name = "jkanime"
            supports_dub = False
            _VALID_URL = r"$^"

            def get_episode(self, identifier, episode, dub=False):
                calls.append("jkanime")
                raise RuntimeError("offline")

        class AnimeFLV:
            site_name = "animeflv"
            supports_dub = True
            _VALID_URL = r"$^"

            def search(self, title, dub=False):
                calls.append("animeflv-search")
                return [{
                    "id": "animeflv:https://example/anime/frieren",
                    "title": title,
                    "total_episodes": 28,
                    "extractor": "animeflv",
                }]

            def get_episode(self, identifier, episode, dub=False):
                calls.append("animeflv")
                return {
                    "url": "https://media.example/1.m3u8",
                    "referer": "https://embed.example/",
                    "extractor": "animeflv",
                }

        result = AnimeExtractor((Jkanime, AnimeFLV)).get_episode(
            "jkanime:https://jkanime.net/frieren/",
            "1",
            title="Frieren",
        )

        self.assertEqual(result["extractor"], "animeflv")
        self.assertEqual(calls, ["jkanime", "animeflv-search", "animeflv"])

    def test_dub_mode_skips_non_dub_sources(self):
        class Jkanime:
            site_name = "jkanime"
            supports_dub = False
            _VALID_URL = r"$^"

            def search(self, title, dub=False):
                raise AssertionError("JKanime must not run for Spanish dub")

        class AnimeFLV:
            site_name = "animeflv"
            supports_dub = True
            _VALID_URL = r"$^"

            def search(self, title, dub=False):
                return [{
                    "id": "animeflv:id",
                    "title": title,
                    "total_episodes": 4,
                    "extractor": "animeflv",
                }]

        results = AnimeExtractor((Jkanime, AnimeFLV)).search("Frieren", dub=True)

        self.assertEqual([item["extractor"] for item in results], ["animeflv"])


if __name__ == "__main__":
    unittest.main()
