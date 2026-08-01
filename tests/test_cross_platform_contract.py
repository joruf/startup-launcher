"""Contract tests for Startup Launcher (Linux-focused, no GUI required)."""

from __future__ import annotations

import unittest
from pathlib import Path

import json_store
import paths


class TestPathsContract(unittest.TestCase):
    def test_project_root_has_run_py(self) -> None:
        self.assertTrue((paths.PROJECT_ROOT / "run.py").is_file())

    def test_example_entries_exist(self) -> None:
        self.assertTrue(paths.EXAMPLE_ENTRIES_FILE.is_file())

    def test_resources_icon_or_desktop_template(self) -> None:
        self.assertTrue(paths.RESOURCES_DIR.is_dir())
        self.assertTrue(
            paths.DESKTOP_TEMPLATE.is_file() or paths.ICON_FILE.is_file()
        )


class TestJsonStoreContract(unittest.TestCase):
    def test_load_example_entries_shape(self) -> None:
        data = json_store.load_json(paths.EXAMPLE_ENTRIES_FILE, default=[])
        self.assertIsInstance(data, (list, dict))


class TestModuleImports(unittest.TestCase):
    def test_import_models_and_services(self) -> None:
        import models.entries  # noqa: F401
        import services.launcher  # noqa: F401
        import services.single_instance  # noqa: F401


if __name__ == "__main__":
    unittest.main()
