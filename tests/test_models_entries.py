"""Behavior tests for the entry schema, seeding, and persistence in models/entries.py."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import entries as entry_model


def _sample_entry(**overrides):
    entry = {
        "id": "abc123",
        "name": "Browser",
        "group": "",
        "command": "firefox",
        "window_mode": "normal",
        "match_mode": "class",
        "match_string": "Firefox",
        "delay_seconds": 0,
        "enabled": True,
    }
    entry.update(overrides)
    return entry


class TestClampDelaySeconds(unittest.TestCase):
    def test_within_range_is_unchanged(self):
        self.assertEqual(entry_model.clamp_delay_seconds(30), 30)

    def test_below_minimum_is_clamped_up(self):
        self.assertEqual(entry_model.clamp_delay_seconds(-5), entry_model.MIN_DELAY_SECONDS)

    def test_above_maximum_is_clamped_down(self):
        self.assertEqual(entry_model.clamp_delay_seconds(999), entry_model.MAX_DELAY_SECONDS)


class TestNewId(unittest.TestCase):
    def test_ids_are_unique(self):
        self.assertNotEqual(entry_model.new_id(), entry_model.new_id())


class TestExistingGroups(unittest.TestCase):
    def test_returns_sorted_unique_non_empty_group_names(self):
        entries = [
            _sample_entry(group="VSCode"),
            _sample_entry(group=""),
            _sample_entry(group="Browsers"),
            _sample_entry(group="VSCode"),
            _sample_entry(group="  "),
        ]
        self.assertEqual(entry_model.existing_groups(entries), ["Browsers", "VSCode"])


class TestEnsureSchema(unittest.TestCase):
    def test_backfills_missing_id_and_delay(self):
        entries = [{"name": "No id or delay"}]
        changed = entry_model._ensure_schema(entries)
        self.assertTrue(changed)
        self.assertTrue(entries[0]["id"])
        self.assertEqual(entries[0]["delay_seconds"], 0)

    def test_leaves_complete_entries_untouched(self):
        entries = [_sample_entry(id="fixed-id", delay_seconds=5)]
        changed = entry_model._ensure_schema(entries)
        self.assertFalse(changed)
        self.assertEqual(entries[0]["id"], "fixed-id")
        self.assertEqual(entries[0]["delay_seconds"], 5)


class TestLoadSaveEntries(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.entries_file = Path(self._tmpdir.name) / "entries.json"
        self.example_file = Path(self._tmpdir.name) / "entries.example.json"

        self._entries_patch = patch.object(entry_model, "ENTRIES_FILE", self.entries_file)
        self._example_patch = patch.object(entry_model, "EXAMPLE_ENTRIES_FILE", self.example_file)
        self._entries_patch.start()
        self._example_patch.start()
        self.addCleanup(self._entries_patch.stop)
        self.addCleanup(self._example_patch.stop)

    def test_missing_entries_file_seeds_from_example_and_persists_it(self):
        self.example_file.write_text(json.dumps([_sample_entry(id="")]), encoding="utf-8")

        loaded = entry_model.load_entries()

        self.assertEqual(len(loaded), 1)
        self.assertTrue(loaded[0]["id"], "missing id should have been backfilled")
        self.assertTrue(self.entries_file.is_file(), "seeded entries should be persisted")

    def test_missing_entries_file_and_no_example_seeds_empty_list(self):
        loaded = entry_model.load_entries()
        self.assertEqual(loaded, [])

    def test_corrupted_entries_file_falls_back_to_seed(self):
        self.entries_file.write_text("{not json", encoding="utf-8")
        loaded = entry_model.load_entries()
        self.assertEqual(loaded, [])

    def test_existing_valid_entries_are_returned_as_is(self):
        entry_model.save_entries([_sample_entry(name="Existing")])
        loaded = entry_model.load_entries()
        self.assertEqual(loaded[0]["name"], "Existing")

    def test_loading_backfills_schema_and_rewrites_file(self):
        self.entries_file.write_text(json.dumps([{"name": "Legacy entry"}]), encoding="utf-8")

        loaded = entry_model.load_entries()

        self.assertTrue(loaded[0]["id"])
        self.assertEqual(loaded[0]["delay_seconds"], 0)
        on_disk = json.loads(self.entries_file.read_text(encoding="utf-8"))
        self.assertTrue(on_disk[0]["id"], "backfilled schema should be persisted, not just in memory")

    def test_save_entries_round_trips(self):
        entries = [_sample_entry(name="A"), _sample_entry(name="B", id="second")]
        entry_model.save_entries(entries)
        on_disk = json.loads(self.entries_file.read_text(encoding="utf-8"))
        self.assertEqual([e["name"] for e in on_disk], ["A", "B"])


if __name__ == "__main__":
    unittest.main()
