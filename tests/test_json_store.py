"""Behavior tests for json_store's atomic write / resilient read helpers."""

import json
import tempfile
import unittest
from pathlib import Path

import json_store


class TestLoadJson(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.dir = Path(self._tmpdir.name)

    def test_missing_file_returns_default(self):
        path = self.dir / "missing.json"
        self.assertEqual(json_store.load_json(path, default=[1, 2, 3]), [1, 2, 3])

    def test_valid_file_is_parsed(self):
        path = self.dir / "data.json"
        path.write_text('{"a": 1}', encoding="utf-8")
        self.assertEqual(json_store.load_json(path, default={}), {"a": 1})

    def test_corrupted_file_returns_default_instead_of_raising(self):
        path = self.dir / "broken.json"
        path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(json_store.load_json(path, default="fallback"), "fallback")

    def test_empty_file_returns_default_instead_of_raising(self):
        path = self.dir / "empty.json"
        path.write_text("", encoding="utf-8")
        self.assertEqual(json_store.load_json(path, default=[]), [])


class TestSaveJsonAtomic(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.dir = Path(self._tmpdir.name)

    def test_writes_readable_json(self):
        path = self.dir / "out.json"
        json_store.save_json_atomic(path, {"x": [1, 2, 3]})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"x": [1, 2, 3]})

    def test_overwrites_existing_file(self):
        path = self.dir / "out.json"
        json_store.save_json_atomic(path, {"version": 1})
        json_store.save_json_atomic(path, {"version": 2})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"version": 2})

    def test_no_leftover_temp_files_after_a_successful_write(self):
        path = self.dir / "out.json"
        json_store.save_json_atomic(path, {"a": 1})
        leftovers = [p for p in self.dir.iterdir() if p.name != "out.json"]
        self.assertEqual(leftovers, [])

    def test_preserves_non_ascii_characters(self):
        path = self.dir / "out.json"
        json_store.save_json_atomic(path, {"name": "Öffnen ähnliche Größe"})
        self.assertEqual(
            json.loads(path.read_text(encoding="utf-8"))["name"], "Öffnen ähnliche Größe"
        )

    def test_failed_write_does_not_touch_existing_file_and_cleans_up_temp(self):
        path = self.dir / "out.json"
        json_store.save_json_atomic(path, {"safe": True})

        class Unserializable:
            pass

        with self.assertRaises(TypeError):
            json_store.save_json_atomic(path, {"bad": Unserializable()})

        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"safe": True})
        leftovers = [p for p in self.dir.iterdir() if p.name != "out.json"]
        self.assertEqual(leftovers, [])


if __name__ == "__main__":
    unittest.main()
