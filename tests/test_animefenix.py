# tests/test_animefenix.py
import unittest
from unittest.mock import Mock, patch
from extractors.animefenix import AnimeFenixExtractor


class TestAnimeFenixExtractor(unittest.TestCase):
    def setUp(self):
        self.extractor = AnimeFenixExtractor()
        self.extractor._log = Mock()  # silenciar logs en consola durante el test

    SEARCH_HTML = """
    <html>
        <body>
            <div class="animes-list">
                <a href="/ore-dake-level-up-na-ken">
                    <div class="title">Ore dake Level Up na Ken</div>
                </a>
                <a href="/directorio/anime?q=test" class="nav-link">Siguiente</a>
                <a href="/ver/ore-dake-level-up-na-ken-1">Capítulo 1 (Ignorar)</a>
            </div>
        </body>
    </html>
    """

    SERIES_HTML = """
    <html>
        <body>
            <div id="episodes-container" class="grid grid-cols-2 gap-4 md:grid-cols-2 lg:grid-cols-4 xl:grid-cols-5 xl:gap-6">
                <a href="/ver/ore-dake-level-up-na-ken-1" class="episode-card">
                    <span class="ep-title">Capítulo 1</span>
                </a>
                <a href="/ver/ore-dake-level-up-na-ken-2" class="episode-card">
                    <span class="ep-title">Capítulo 2</span>
                </a>
                <a href="/ver/ore-dake-level-up-na-ken-3" class="episode-card">
                    <span class="ep-title">Capítulo 3</span>
                </a>
            </div>
        </body>
    </html>
    """

    EPISODE_HTML = """
    <html>
        <body>
            <ul class="is-borderless episode-page__servers-list" style="background-color:black;">
                <li class="">
                    <a title="PlusTube" href="#vid1"><span>PlusTube</span></a>
                </li>
                <li class="is-active">
                    <a title="PlusRise" href="#vid2"><span>PlusRise</span></a>
                </li>
                <li>
                    <a title="Mp4Upload" href="#vid5"><span>Mp4Upload</span></a>
                </li>
            </ul>

            <div class="iframe-container" id="video_player">
                <iframe src="https://re.animepelix.net/redirect.php?id=https://re.ironhentai.com/embed.php?id=65998ef2811f9" frameborder="0"></iframe>
            </div>

            <script>
                var string_tabs = [
                    "https://re.animepelix.net/redirect.php?id=https://re.ironhentai.com/vt.php?id=zado5dcofj9s",
                    "https://re.animepelix.net/redirect.php?id=https://www.mp4upload.com/embed-m374rqjhedrc.html"
                ];
            </script>
        </body>
    </html>
    """

    @patch.object(AnimeFenixExtractor, '_download_webpage')
    def test_search(self, mock_download):
        mock_download.return_value = self.SEARCH_HTML
        
        with patch.object(AnimeFenixExtractor, 'list_episodes') as mock_list_ep:
            mock_list_ep.return_value = ['1', '2', '3']
            
            results = self.extractor.search("ore dake level")
            expected_url = self.extractor.base_url + "/directorio/anime?q=ore+dake+level"
            
            mock_download.assert_called_once_with(expected_url)
            self.assertEqual(len(results), 1)
            self.assertEqual(results[0]['id'], f"animefenix:{self.extractor.base_url}/ore-dake-level-up-na-ken")
            self.assertEqual(results[0]['title'], "Ore dake Level Up na Ken")  # <-- Corregido aquí
            self.assertEqual(results[0]['total_episodes'], 3)
            mock_list_ep.assert_called_once_with(
                f"animefenix:{self.extractor.base_url}/ore-dake-level-up-na-ken"
            )

    @patch.object(AnimeFenixExtractor, '_download_webpage')
    def test_list_episodes(self, mock_download):
        mock_download.return_value = self.SERIES_HTML
        
        episodes = self.extractor.list_episodes("ore-dake-level-up-na-ken")
        expected_url = f"{self.extractor.base_url}/ore-dake-level-up-na-ken"
        
        mock_download.assert_called_once_with(expected_url)
        self.assertEqual(episodes, ['1', '2', '3'])

    @patch.object(AnimeFenixExtractor, '_download_webpage')
    def test_extract(self, mock_download):
        mock_download.return_value = self.EPISODE_HTML

        test_url = "https://animefenix2.tv/ver/ore-dake-level-up-na-ken-1"
        result = self.extractor.extract(test_url)

        mock_download.assert_called_once_with(test_url)
        formats = result['formats']

        self.assertGreaterEqual(len(formats), 1)

        # Formato 1: El del iframe activo por defecto (PlusRise tiene la clase .is-active)
        self.assertEqual(
            formats[0]['url'],
            "https://re.ironhentai.com/embed.php?id=65998ef2811f9",
        )
        self.assertEqual(formats[0]['http_headers']['Referer'], test_url)

        # Metadatos globales devueltos
        self.assertEqual(result['id'], 'ore-dake-level-up-na-ken-1')
        self.assertEqual(result['title'], 'Ore Dake Level Up Na Ken - Episodio 1')
        self.assertEqual(result['extractor'], 'animefenix')

    @patch.object(AnimeFenixExtractor, '_download_webpage')
    def test_extract_no_player_block(self, mock_download):
        mock_download.return_value = "<html><body>Contenido vacío sin reproductores</body></html>"
        test_url = "https://animefenix2.tv/ver/ore-dake-level-up-na-ken-1"
        
        with self.assertRaisesRegex(RuntimeError, "No se encontró el bloque de reproducción"):
            self.extractor.extract(test_url)

    @patch.object(AnimeFenixExtractor, '_download_webpage')
    def test_list_episodes_no_container(self, mock_download):
        mock_download.return_value = "<html><body>No episodes here</body></html>"
        
        with self.assertRaisesRegex(RuntimeError, "No se encontraron episodios"):
            self.extractor.list_episodes("slug-vacio")


if __name__ == "__main__":
    unittest.main()
