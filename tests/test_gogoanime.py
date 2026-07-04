import unittest
from unittest.mock import Mock, patch
import urllib.parse
from extractors.gogoanime import GogoanimeExtractor


class TestGogoanimeExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = GogoanimeExtractor()
        self.extractor._log = Mock()  # silenciar logs

    SEARCH_HTML = """
    <html>
        <body>
            <div class="items">
                <a href="/series/ore-dake-level-up-na-ken/">Ore dake Level Up na Ken</a>
                <a href="/series/solo-leveling/">Solo Leveling</a>
                <a href="/series/one-piece/">One Piece</a>
            </div>
        </body>
    </html>
    """

    SERIES_HTML = """
    <html>
        <body>
            <div class="episode-list">
                <a href="/ore-dake-level-up-na-ken-episode-1-english-subbed/">Episode 1</a>
                <a href="/ore-dake-level-up-na-ken-episode-2-english-subbed/">Episode 2</a>
                <a href="/ore-dake-level-up-na-ken-episode-3-english-subbed/">Episode 3</a>
                <a href="/ore-dake-level-up-na-ken-episode-4-english-subbed/">Episode 4</a>
            </div>
        </body>
    </html>
    """

    EPISODE_HTML = """
    <html>
        <body>
            <div class="servers">
                <ul>
                    <li class="player-type-link active"
                        data-type="Blogger"
                        data-encrypted-url1="eEZiemFIYjJGTStianlNa1NRcHRkUE1RU3prV0tXYWdTUjBZUUQ2YlJiai9VYVpLRmJoajdFbVdlTm5DWlRNZ1AvMklYak1lRUdZcVc3R0tTb2tzSmVxL0hLdFpDRGNPWjdBTS9iR0tmbjA9"
                        data-encrypted-url2="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-encrypted-url3="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-ref="gogoanime.by">
                        Fast Server
                    </li>
                    <li class="player-type-link"
                        data-type="embed"
                        data-encrypted-url1="QjlrUk16WG80dkIvOU0vNE81cmxLOVM5Z1VIb1Z0dkthZlBVRHNlRU0xMFdaWmR0ZU12VE1uckFibzgydkZoLw=="
                        data-encrypted-url2="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-encrypted-url3="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-ref="gogoanime.by"
                        data-plain-url="https://megavid.buzz/embed/aB4XQpbv6IF02mV">
                        HD
                    </li>
                    <li class="player-type-link"
                        data-type="hianime"
                        data-encrypted-url1="QWt2QXFMekR6Q1hXNUxCYXhlUEFyREJ1OWVYaHhiSDB1UWtXVUp1RXBCZi9ycld4ajljMkJWTFZXa3FhN1RFaWlSaDdzaXpDaTE0WEl3K2k1TXdjd3Rxa05Bd09uNXEzR2tsWXJoeHRqR1ZEUm0vUmZBZE9sc3U0eXNVOXV1MWd1d2ZXMFVaUkF3RVRWOXJmUFdYNnIxZ1dQZ1RCVlhKSTZZT2IxREN0RGFCdmN1ZXhBVWFVTTdVaWZJT0sydXFzOUd6VnFJZTBVZjl5N2hQTWlnSlNNdjdiMXNjSG00VjZhcm11RkwxM3luZz0="
                        data-encrypted-url2="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-encrypted-url3="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-ref="gogoanime.by">
                        VidSrc
                    </li>
                    <li class="player-type-link"
                        data-type="hianime"
                        data-encrypted-url1="QWt2QXFMekR6Q1hXNUxCYXhlUEFyREJ1OWVYaHhiSDB1UWtXVUp1RXBCZi9ycld4ajljMkJWTFZXa3FhN1RFaWlSaDdzaXpDaTE0WEl3K2k1TXdjd3Rxa05Bd09uNXEzR2tsWXJoeHRqR1ZEUm0vUmZBZE9sc3U0eXNVOXV1MWd1d2ZXMFVaUkF3RVRWOXJmUFdYNnIxZ1dQZ1RCVlhKSTZZT2IxREN0RGFCdmN1ZXhBVWFVTTdVaWZJT0sydXFzTXVNOXlteE44dEFaM09pL0JQZzdCcStqanY1T1MwRFBJTG1tblp6emVJOD0="
                        data-encrypted-url2="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-encrypted-url3="aEtKUFNZNUdLeGNqTlhWeThhdjNLdz09"
                        data-ref="gogoanime.by">
                        MegaCloud
                    </li>
                </ul>
            </div>
            <script>
                var defaultPostId = "19619";
            </script>
        </body>
    </html>
    """

    @patch.object(GogoanimeExtractor, '_download_webpage')
    def test_search(self, mock_download):
        mock_download.return_value = self.SEARCH_HTML
        with patch.object(GogoanimeExtractor, 'list_episodes') as mock_list_ep:
            mock_list_ep.return_value = ['1', '2', '3']
            results = self.extractor.search("ore dake level")
            expected_url = self.extractor.base_url + "/?s=ore+dake+level"
            mock_download.assert_called_once_with(expected_url)
            self.assertEqual(len(results), 3)
            self.assertEqual(results[0]['id'], f"gogoanime:{self.extractor.base_url}/series/ore-dake-level-up-na-ken/")
            self.assertEqual(results[0]['title'], "Ore dake Level Up na Ken")
            self.assertEqual(results[0]['total_episodes'], 3)
            self.assertEqual(mock_list_ep.call_count, 3)

    @patch.object(GogoanimeExtractor, '_download_webpage')
    def test_list_episodes(self, mock_download):
        mock_download.return_value = self.SERIES_HTML
        episodes = self.extractor.list_episodes("ore-dake-level-up-na-ken")
        expected_url = f"{self.extractor.base_url}/series/ore-dake-level-up-na-ken"
        mock_download.assert_called_once_with(expected_url)
        self.assertEqual(episodes, ['1', '2', '3', '4'])

    @patch.object(GogoanimeExtractor, '_download_webpage')
    def test_extract(self, mock_download):
        mock_download.return_value = self.EPISODE_HTML

        test_url = "https://gogoanime.by/ore-dake-level-up-na-ken-episode-1-english-subbed/"
        result = self.extractor.extract(test_url)

        self.assertEqual(mock_download.call_args_list[0].args, (test_url,))
        formats = result['formats']

        self.assertGreaterEqual(len(formats), 1)
        
        # Servidor 1: Blogger (player.php)
        self.assertIn("player.php?Blogger=eEZiemFIYjJGTStianlNa1NRcHRkUE1RU3prV0tXYWdTUjBZUUQ2YlJiai9VYVpLRmJoajdFbVdlTm5DWlRNZ1AvMklYak1lRUdZcVc3R0tTb2tzSmVxL0hLdFpDRGNPWjdBTS9iR0tmbjA9", formats[0]['url'])
        self.assertEqual(formats[0]['http_headers']['Referer'], test_url)

        # Metadatos globales devueltos por el extractor
        self.assertEqual(result['id'], 'ore-dake-level-up-na-ken-1')
        self.assertEqual(result['title'], 'Ore Dake Level Up Na Ken - Episodio 1')
        self.assertEqual(result['extractor'], 'gogoanime')

    @patch.object(GogoanimeExtractor, '_download_webpage')
    def test_extract_no_servers(self, mock_download):
        mock_download.return_value = "<html><body>No servers</body></html>"
        test_url = "https://gogoanime.by/ore-dake-level-up-na-ken-episode-1-english-subbed/"
        with self.assertRaisesRegex(RuntimeError, "No se encontró el bloque de servidores"):
            self.extractor.extract(test_url)

    @patch.object(GogoanimeExtractor, '_download_webpage')
    def test_list_episodes_no_episodes(self, mock_download):
        mock_download.return_value = "<html><body>No episodes</body></html>"
        with self.assertRaisesRegex(RuntimeError, "No se encontraron episodios"):
            self.extractor.list_episodes("some-series")


if __name__ == "__main__":
    unittest.main()
