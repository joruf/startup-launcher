"""Behavior tests for window_geometry.json persistence in models/geometry.py."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from models import geometry as geometry_model


class TestLoadSaveGeometry(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.geometry_file = Path(self._tmpdir.name) / "window_geometry.json"
        patcher = patch.object(geometry_model, "GEOMETRY_FILE", self.geometry_file)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_missing_file_returns_empty_dict(self):
        self.assertEqual(geometry_model.load_geometry(), {})

    def test_round_trips_saved_positions(self):
        data = {"entry-1": {"x": 10, "y": 20, "width": 800, "height": 600}}
        geometry_model.save_geometry(data)
        self.assertEqual(geometry_model.load_geometry(), data)

    def test_save_overwrites_previous_contents(self):
        geometry_model.save_geometry({"entry-1": {"x": 0, "y": 0, "width": 100, "height": 100}})
        geometry_model.save_geometry({"entry-2": {"x": 5, "y": 5, "width": 200, "height": 200}})
        self.assertEqual(list(geometry_model.load_geometry().keys()), ["entry-2"])


if __name__ == "__main__":
    unittest.main()
