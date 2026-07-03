import unittest
import re
from extractor import JkanimeExtractor

class TestJkanimeExtractor(unittest.TestCase):

    def setUp(self):
        """Inicializa el extractor antes de cada prueba."""
        self.extractor = JkanimeExtractor()

    def test_validez_url_correcta(self):
        """Prueba que la expresión regular acepte URLs válidas de episodios con y sin diagonal."""
        patron = self.extractor._VALID_URL
        
        # Caso 1: Con barra inclinada al final
        url_con_barra = "https://jkanime.net/one-piece/1168/"
        match1 = re.match(patron, url_con_barra)
        self.assertIsNotNone(match1, "Falló con barra inclinada final")
        self.assertEqual(match1.group('anime_id'), 'one-piece')
        self.assertEqual(match1.group('ep_no'), '1168')

        # Caso 2: Sin barra inclinada al final
        url_sin_barra = "https://jkanime.net/mairimashita-iruma-kun-4th-season/13"
        match2 = re.match(patron, url_sin_barra)
        self.assertIsNotNone(match2, "Falló sin barra inclinada final")
        self.assertEqual(match2.group('anime_id'), 'mairimashita-iruma-kun-4th-season')
        self.assertEqual(match2.group('ep_no'), '13')

    def test_validez_url_incorrecta(self):
        """Prueba que el extractor rechace URLs inválidas o páginas que no son episodios."""
        url_invalida = "https://youtube.com"
        url_raiz = "https://jkanime.net/"
        
        with self.assertRaises(ValueError):
            self.extractor.extract(url_invalida)
            
        with self.assertRaises(ValueError):
            self.extractor.extract(url_raiz)

if __name__ == '__main__':
    unittest.main()
