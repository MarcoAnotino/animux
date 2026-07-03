import unittest
from unittest.mock import Mock

from extractor import AnimeExtractor, AnimeFLVExtractor, JkanimeExtractor


class TestAnimeFLVExtractor(unittest.TestCase):
    url = (
        "https://vww.animeflv.one/ver/"
        "tensei-shitara-slime-datta-ken-4th-season-10"
    )
    iframe_url = "https://q8y5z.com/b22/xejjvjfoy338?autoplay=1"
    stream_url = "https://media.example/master.m3u8?token=abc"

    def setUp(self):
        self.extractor = AnimeFLVExtractor()
        self.extractor._get_iframes_from_ajax = Mock(
            return_value=[self.iframe_url]
        )
        self.extractor._extract_video_from_iframes = Mock(
            return_value=(self.stream_url, self.iframe_url)
        )
        self.extractor._get_url_via_ytdlp = Mock(return_value=None)

    def test_builds_result_from_internal_iframe_extraction(self):
        result = self.extractor.extract(self.url)

        self.assertEqual(result["id"], "tensei-shitara-slime-datta-ken-4th-season-10")
        self.assertEqual(result["extractor"], "animeflv")
        self.assertEqual(result["formats"][0]["url"], self.stream_url)
        self.assertEqual(result["formats"][0]["protocol"], "m3u8_native")
        self.assertEqual(
            result["formats"][0]["http_headers"]["Referer"], self.iframe_url
        )

        self.extractor._get_iframes_from_ajax.assert_called_once_with(self.url)
        self.extractor._extract_video_from_iframes.assert_called_once_with(
            [self.iframe_url], self.url
        )
        self.extractor._get_url_via_ytdlp.assert_not_called()

    def test_marks_non_hls_fallback_as_https(self):
        fallback_url = "https://fallback.example/video.mp4"
        self.extractor._extract_video_from_iframes.return_value = (
            fallback_url,
            self.iframe_url,
        )

        result = self.extractor.extract(self.url)

        self.assertEqual(result["formats"][0]["protocol"], "https")

    def test_falls_back_to_ytdlp_when_api_has_no_stream(self):
        fallback_url = "https://fallback.example/video.mp4"
        self.extractor._extract_video_from_iframes.return_value = (None, None)
        self.extractor._get_url_via_ytdlp.return_value = fallback_url

        result = self.extractor.extract(self.url)

        self.assertEqual(result["formats"][0]["url"], fallback_url)
        self.extractor._get_url_via_ytdlp.assert_called_once_with(
            self.url, referer=self.url
        )

    def test_rejects_page_without_internal_iframes(self):
        self.extractor._get_iframes_from_ajax.return_value = []

        with self.assertRaisesRegex(RuntimeError, "obtener los iframes"):
            self.extractor.extract(self.url)

    def test_rejects_invalid_url(self):
        with self.assertRaises(ValueError):
            self.extractor.extract("https://example.com/video/1")


class TestAnimeExtractor(unittest.TestCase):
    def test_routes_animeflv_urls(self):
        orchestrator = AnimeExtractor()
        animeflv = next(
            extractor
            for extractor in orchestrator._extractors
            if isinstance(extractor, AnimeFLVExtractor)
        )
        animeflv.extract = Mock(return_value={"extractor": "animeflv"})

        result = orchestrator.extract(TestAnimeFLVExtractor.url)

        self.assertEqual(result, {"extractor": "animeflv"})
        animeflv.extract.assert_called_once()
        self.assertEqual(
            animeflv.extract.call_args.args[1].group("ep_no"),
            "10",
        )

    def test_routes_jkanime_urls(self):
        orchestrator = AnimeExtractor()
        jkanime = next(
            extractor
            for extractor in orchestrator._extractors
            if isinstance(extractor, JkanimeExtractor)
        )
        jkanime.extract = Mock(return_value={"extractor": "jkanime"})

        result = orchestrator.extract("https://jkanime.net/one-piece/1/")

        self.assertEqual(result, {"extractor": "jkanime"})
        jkanime.extract.assert_called_once()

    def test_accepts_an_injected_extractor_registry(self):
        class FutureExtractor:
            _VALID_URL = r"https://future\.example/(?P<id>[0-9]+)"

            def extract(self, url, match=None):
                return {"extractor": "future", "id": match.group("id")}

        result = AnimeExtractor((FutureExtractor,)).extract(
            "https://future.example/42"
        )

        self.assertEqual(result, {"extractor": "future", "id": "42"})

    def test_rejects_unsupported_urls(self):
        with self.assertRaisesRegex(ValueError, "Ningún extractor interno"):
            AnimeExtractor().extract("https://example.com/video/1")


if __name__ == "__main__":
    unittest.main()
