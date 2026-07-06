import json
import os
import pathlib
import subprocess
import tempfile
import unittest


ROOT = pathlib.Path(__file__).resolve().parents[1]
HELPER = ROOT / "animux-library"
ANIMUX = ROOT / "animux"


class LibraryHelperTest(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.tempdir.name) / "state" / "library.json"

    def tearDown(self):
        self.tempdir.cleanup()

    def run_helper(self, *args, check=True):
        return subprocess.run(
            [str(HELPER), "--file", str(self.path), *args],
            check=check,
            text=True,
            capture_output=True,
        )

    def data(self):
        return json.loads(self.path.read_text(encoding="utf-8"))

    def add(self, anime_id="provider:one", title="One", status="watch_later", total="3"):
        self.run_helper(
            "upsert",
            "--id",
            anime_id,
            "--title",
            title,
            "--status",
            status,
            "--language",
            "es",
            "--mode",
            "dub",
            "--provider",
            "python-extractor",
            "--total",
            total,
        )

    def test_init_creates_library_when_missing(self):
        self.run_helper("init")
        self.assertEqual({}, self.data())
        self.assertEqual(0o600, self.path.stat().st_mode & 0o777)

    def test_add_watch_later_and_mark_watching(self):
        self.add()
        self.assertEqual("watch_later", self.data()["provider:one"]["status"])
        self.run_helper("status", "--id", "provider:one", "--status", "watching")
        self.assertEqual("watching", self.data()["provider:one"]["status"])

    def test_watch_tracks_episode_once_and_promotes_watch_later(self):
        self.add()
        for _ in range(2):
            self.run_helper(
                "watch",
                "--id",
                "provider:one",
                "--title",
                "One",
                "--episode",
                "1",
                "--total",
                "3",
            )
        entry = self.data()["provider:one"]
        self.assertEqual(["1"], entry["watched_episodes"])
        self.assertEqual("1", entry["last_episode"])
        self.assertEqual("watching", entry["status"])

    def test_last_known_episode_marks_completed_without_inventing_episodes(self):
        self.add(total="3")
        self.run_helper(
            "watch",
            "--id",
            "provider:one",
            "--title",
            "One",
            "--episode",
            "3",
            "--total",
            "3",
        )
        entry = self.data()["provider:one"]
        self.assertEqual("completed", entry["status"])
        self.assertIsNotNone(entry["completed_at"])
        self.assertEqual(["3"], entry["watched_episodes"])

    def test_completed_is_alphabetical(self):
        self.add("provider:z", "Zulu", "completed")
        self.add("provider:a", "Alpha", "completed")
        rows = self.run_helper("list", "--view", "completed").stdout.splitlines()
        self.assertEqual(["Alpha", "Zulu"], [row.split("\t")[2] for row in rows])

    def test_favorite_is_independent_from_status(self):
        self.add(status="completed")
        self.run_helper("favorite", "--id", "provider:one", "--value", "true")
        self.run_helper("status", "--id", "provider:one", "--status", "dropped")
        entry = self.data()["provider:one"]
        self.assertTrue(entry["favorite"])
        self.assertEqual("dropped", entry["status"])
        favorite_rows = self.run_helper("list", "--view", "favorites").stdout
        self.assertIn("provider:one", favorite_rows)

    def test_corrupt_json_reports_error_without_overwriting(self):
        self.path.parent.mkdir(parents=True)
        original = '{"broken": '
        self.path.write_text(original, encoding="utf-8")
        result = self.run_helper("init", check=False)
        self.assertEqual(2, result.returncode)
        self.assertIn("invalid JSON", result.stderr)
        self.assertIn("Data was not changed", result.stderr)
        self.assertEqual(original, self.path.read_text(encoding="utf-8"))


class ShellIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = ANIMUX.read_text(encoding="utf-8")

    def test_episode_or_index_bypasses_action_menu(self):
        self.assertIn(
            '[ -z "${ep_no:-}" ] && [ -z "${index:-}" ] && [ -t 0 ] && [ -t 1 ]',
            self.source,
        )
        self.assertIn("if offer_anime_actions; then", self.source)

    def test_existing_history_is_still_updated(self):
        playback_tail = self.source.split("play_episode() {", 1)[1].split("play() {", 1)[0]
        self.assertIn("update_history", playback_tail)
        self.assertIn("library_record_progress", playback_tail)
        self.assertIn('histfile="$hist_dir/ani-hsts"', self.source)

    def test_library_preview_reuses_cover_pipeline_and_respects_art_flags(self):
        preview = self.source.split("library_preview_render() {", 1)[1].split("ui_rule() {", 1)[0]
        self.assertIn("ui_fetch_cover_file", preview)
        self.assertIn("ui_render_cover", preview)
        self.assertIn("ANIMUX_LIBRARY_ART", preview)
        self.assertIn("ANI_CLI_EPISODE_ART", preview)


if __name__ == "__main__":
    unittest.main()
