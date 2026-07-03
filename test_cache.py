import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parent
ANIMUX = ROOT / "animux"


class TestMetadataCache(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        source = ANIMUX.read_text(encoding="utf-8")
        start = source.index("# Metadata cache.")
        end = source.index("\nfind_runtime_file()", start)
        cls.source = source
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.helper = pathlib.Path(cls.tempdir.name) / "cache-helpers.sh"
        cls.helper.write_text(source[start:end] + "\n", encoding="utf-8")

    @classmethod
    def tearDownClass(cls):
        cls.tempdir.cleanup()

    def run_shell(self, body):
        with tempfile.TemporaryDirectory() as cache_dir:
            env = os.environ.copy()
            env.update(
                {
                    "CACHE_HELPER": str(self.helper),
                    "TEST_CACHE": cache_dir,
                    "LC_ALL": "C",
                }
            )
            return subprocess.run(
                ["sh", "-c", '. "$CACHE_HELPER"\n' + body],
                check=True,
                capture_output=True,
                env=env,
                text=True,
            ).stdout

    def test_second_identical_request_uses_cache(self):
        output = self.run_shell(
            r'''
animux_cache_enabled=1
animux_cache_root=$TEST_CACHE
counter=$TEST_CACHE/counter
fetch_metadata() {
    count=$(cat "$counter" 2>/dev/null || printf 0)
    count=$((count + 1))
    printf '%s\n' "$count" >"$counter"
    printf '%s\n' 'id-1 title (12 episodes)'
}
first=$(cache_get_or_run search 21600 'language=es|mode=sub|provider=jkanime|query=frieren' fetch_metadata)
second=$(cache_get_or_run search 21600 'language=es|mode=sub|provider=jkanime|query=frieren' fetch_metadata)
printf '%s|%s|%s|%s\n' "$first" "$second" "$(cat "$counter")" "$(find "$TEST_CACHE/search" -type f | wc -l | tr -d ' ')"
'''
        )
        self.assertEqual(
            output.strip(),
            "id-1 title (12 episodes)|id-1 title (12 episodes)|1|1",
        )

    def test_disabled_cache_always_fetches_and_writes_nothing(self):
        output = self.run_shell(
            r'''
animux_cache_enabled=0
animux_cache_root=$TEST_CACHE
counter=$TEST_CACHE/counter
fetch_metadata() {
    count=$(cat "$counter" 2>/dev/null || printf 0)
    count=$((count + 1))
    printf '%s\n' "$count" >"$counter"
    printf '%s\n' metadata
}
cache_get_or_run search 21600 key fetch_metadata >/dev/null
cache_get_or_run search 21600 key fetch_metadata >/dev/null
files=$(find "$TEST_CACHE" -type f ! -name counter | wc -l | tr -d ' ')
printf '%s|%s\n' "$(cat "$counter")" "$files"
'''
        )
        self.assertEqual(output.strip(), "2|0")

    def test_empty_results_are_not_cached(self):
        output = self.run_shell(
            r'''
animux_cache_enabled=1
animux_cache_root=$TEST_CACHE
counter=$TEST_CACHE/counter
fetch_empty() {
    count=$(cat "$counter" 2>/dev/null || printf 0)
    count=$((count + 1))
    printf '%s\n' "$count" >"$counter"
}
cache_get_or_run episodes 86400 key fetch_empty >/dev/null
cache_get_or_run episodes 86400 key fetch_empty >/dev/null
files=$(find "$TEST_CACHE" -type f ! -name counter | wc -l | tr -d ' ')
printf '%s|%s\n' "$(cat "$counter")" "$files"
'''
        )
        self.assertEqual(output.strip(), "2|0")

    def test_expired_entry_is_refetched(self):
        output = self.run_shell(
            r'''
animux_cache_enabled=1
animux_cache_root=$TEST_CACHE
counter=$TEST_CACHE/counter
fetch_metadata() {
    count=$(cat "$counter" 2>/dev/null || printf 0)
    count=$((count + 1))
    printf '%s\n' "$count" >"$counter"
    printf 'metadata-%s\n' "$count"
}
cache_get_or_run episodes 86400 key fetch_metadata >/dev/null
cache_file=$(find "$TEST_CACHE/episodes" -type f | head -n 1)
{ printf '1\n'; sed '1d' "$cache_file"; } >"$cache_file.expired"
mv "$cache_file.expired" "$cache_file"
result=$(cache_get_or_run episodes 86400 key fetch_metadata)
printf '%s|%s\n' "$result" "$(cat "$counter")"
'''
        )
        self.assertEqual(output.strip(), "metadata-2|2")

    def test_keys_are_normalized_and_playback_is_not_cached(self):
        output = self.run_shell(
            r'''
provider=python-extractor
printf '%s|%s|%s\n' \
    "$(normalize_cache_value '  Frieren+++Beyond Journey  ')" \
    "$(cache_provider_for_id 'animeflv:https://example.invalid/anime/frieren')" \
    "$(cache_provider_for_id 'opaque-id')"
'''
        )
        self.assertEqual(
            output.strip(),
            "frieren beyond journey|animeflv|python-extractor",
        )
        playback = self.source.split("get_episode_url() {", 1)[1].split(
            "# search the query", 1
        )[0]
        self.assertNotIn("cache_get_or_run", playback)
        self.assertIn("cache_get_or_run search 21600", self.source)
        self.assertIn("cache_get_or_run episodes 86400", self.source)


if __name__ == "__main__":
    unittest.main()
