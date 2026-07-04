import pathlib
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]


class TestInstaller(unittest.TestCase):
    def test_installs_extractor_package(self):
        source = (ROOT / "install.sh").read_text(encoding="utf-8")
        self.assertIn('[ -d "$source_dir/extractors" ]', source)
        self.assertIn('rm -rf "$libexec_dir/extractors"', source)
        self.assertIn(
            'cp -R "$source_dir/extractors" "$libexec_dir/extractors"', source
        )
        self.assertIn("-type f -name '*.py' -exec chmod 644", source)


if __name__ == "__main__":
    unittest.main()
