"""Tests for the single-file executable: its paths, autostart entry, children and build.

The executable itself is never started here - ``build-exe.py`` does that after
every build.  These tests pretend to be frozen and check that nothing in that
mode reaches for pip, a script or a Python interpreter that is not there, that
nothing is written into the unpacked files, and that the programs started at
login never see the executable's bundled libraries.
"""

import importlib.util
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import bootstrap_ui
import json_store
import paths
import version
from config import autostart
from services import launcher

ROOT = Path(__file__).resolve().parent.parent


def _build_script():
    """Import ``build-exe.py`` (its name is not a module name)."""
    spec = importlib.util.spec_from_file_location("build_exe", str(ROOT / "build-exe.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class FrozenTestCase(unittest.TestCase):
    """Pretends to run as the executable, unpacked into a temporary directory."""

    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        base = Path(self._tmpdir.name)
        self.bundle = base / "_MEIabc"
        self.bundle.mkdir()
        self.executable = base / "bin" / "startup-launcher-linux-x86_64-0.4.6-build17"
        self.executable.parent.mkdir()
        self.executable.write_bytes(b"binary")
        self.data_dir = base / "data"
        self.autostart_dir = base / "autostart"
        for patcher in (
            patch.object(paths, "IS_FROZEN", True),
            patch.object(paths, "USER_DATA_DIR", self.data_dir),
            patch.object(autostart, "AUTOSTART_DIR", self.autostart_dir),
            patch.object(sys, "executable", str(self.executable)),
            patch.object(sys, "_MEIPASS", str(self.bundle), create=True),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)


class TestResourceRoot(unittest.TestCase):
    def test_the_executable_finds_its_resources_in_the_unpacked_data(self):
        with patch.object(sys, "frozen", True, create=True), \
                patch.object(sys, "_MEIPASS", "/tmp/_MEIabc", create=True):
            self.assertEqual(paths._project_root(), Path("/tmp/_MEIabc"))

    def test_a_checkout_finds_its_resources_next_to_the_sources(self):
        self.assertEqual(paths._project_root(), ROOT)
        self.assertEqual(paths.ICON_FILE, ROOT / "resources" / "startup-launcher.png")
        self.assertEqual(paths.EXAMPLE_ENTRIES_FILE, ROOT / "entries.example.json")

    def test_user_data_never_lives_in_the_project_root(self):
        """The unpacked files are deleted when the executable exits."""
        for user_file in (paths.ENTRIES_FILE, paths.GEOMETRY_FILE, paths.SETTINGS_FILE):
            self.assertEqual(user_file.parent, paths.CONFIG_DIR)
            self.assertNotEqual(user_file.parent, paths.PROJECT_ROOT)
        self.assertEqual(paths.CONFIG_DIR.name, "startup-launcher")

    def test_the_first_save_creates_the_config_directory(self):
        with tempfile.TemporaryDirectory() as base:
            target = Path(base) / "config" / "startup-launcher" / "entries.json"
            json_store.save_json_atomic(target, [{"name": "x"}])
            self.assertEqual(json_store.load_json(target, None), [{"name": "x"}])


class TestExecutableName(unittest.TestCase):
    def test_the_name_carries_platform_and_version(self):
        cases = [
            (False, "x86_64", "startup-launcher-linux-x86_64-0.4.6-build17"),
            (False, "aarch64", "startup-launcher-linux-aarch64-0.4.6-build17"),
            (False, "AMD64", "startup-launcher-linux-x86_64-0.4.6-build17"),
            (True, "AMD64", "startup-launcher-windows-x86_64-0.4.6-build17.exe"),
        ]
        for windows, machine, expected in cases:
            with self.subTest(machine=machine, windows=windows), \
                    patch.object(paths, "IS_WINDOWS", windows), \
                    patch.object(paths, "IS_MACOS", False), \
                    patch.object(paths.platform, "machine", return_value=machine):
                self.assertEqual(paths.executable_name("0.4.6", 17), expected)

    def test_the_name_defaults_to_this_version(self):
        found = version.current()
        expected = "{0}-build{1}".format(found.name, int(found.build or 0))
        self.assertTrue(paths.executable_name().endswith(expected))


class TestFrozenVersion(FrozenTestCase):
    def setUp(self):
        super().setUp()
        version.forget()
        self.addCleanup(version.forget)

    def test_the_bundled_file_is_the_answer_and_git_is_never_asked(self):
        (self.bundle / "VERSION").write_text("0.4.6 17 4957c55 2026-09-02 1\n", encoding="utf-8")
        (self.bundle / ".git").mkdir()
        with patch.object(version, "FROZEN", True), \
                patch.object(version, "_git", side_effect=AssertionError("no git")), \
                patch.object(version, "_write", side_effect=AssertionError("no write")):
            found = version.current(self.bundle)
        self.assertEqual(found.label, "0.4.6 (17) · 4957c55 · 02.09.2026")


class TestVersionFlag(unittest.TestCase):
    def test_version_flag_answers_without_a_gui_toolkit(self):
        """build-exe.py checks the finished file this way, headless."""
        probe = (
            "import runpy, sys\n"
            "sys.argv = ['run.py', '--version']\n"
            "try:\n"
            "    runpy.run_path('run.py', run_name='__main__')\n"
            "except SystemExit:\n"
            "    assert 'tkinter' not in sys.modules and 'gi' not in sys.modules, 'GUI imported'\n"
            "    raise\n"
        )
        with tempfile.TemporaryDirectory() as home:
            completed = subprocess.run(
                [sys.executable, "-c", probe], cwd=str(ROOT), capture_output=True, text=True,
                timeout=60, env={"PATH": "/usr/bin:/bin", "HOME": home},
            )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("Startup Launcher " + version.label(ROOT), completed.stdout)


class TestFrozenAutostart(FrozenTestCase):
    def test_the_autostart_entry_starts_the_executable(self):
        autostart.enable()
        content = autostart.desktop_file_path().read_text(encoding="utf-8")
        exec_lines = [line for line in content.splitlines() if line.startswith("Exec=")]
        self.assertEqual(exec_lines, [f'Exec="{self.executable.resolve()}" --autostart'])
        self.assertNotIn("run.py", content)
        self.assertNotIn("Path=", content)
        self.assertNotIn(str(self.bundle), content)

    def test_the_icon_outlives_the_unpacked_files(self):
        autostart.enable()
        content = autostart.desktop_file_path().read_text(encoding="utf-8")
        icon = self.data_dir / paths.ICON_FILE.name
        self.assertIn(f"Icon={icon}", content.splitlines())
        self.assertTrue(icon.is_file())

    def test_an_up_to_date_entry_is_not_rewritten_on_every_start(self):
        autostart.enable()
        self.assertFalse(autostart.is_outdated())
        self.assertFalse(autostart.refresh_if_enabled())

    def test_a_checkout_entry_is_pointed_at_the_executable(self):
        with patch.object(paths, "IS_FROZEN", False):
            autostart.enable()
        self.assertTrue(autostart.refresh_if_enabled())
        content = autostart.desktop_file_path().read_text(encoding="utf-8")
        self.assertIn(f'Exec="{self.executable.resolve()}" --autostart', content)

    def test_a_checkout_keeps_its_interpreter_script_and_working_directory(self):
        with patch.object(paths, "IS_FROZEN", False):
            content = autostart._desktop_entry_content()
        self.assertIn(f'"{paths.MAIN_SCRIPT}" --autostart', content)
        self.assertIn(f"Path={paths.PROJECT_ROOT}", content)
        self.assertIn(f"Icon={paths.ICON_FILE}", content)


class TestNoInterpreter(FrozenTestCase):
    """``sys.executable`` is the program itself: ``-m pip`` would start it again."""

    def test_the_setup_window_never_runs_pip(self):
        need = bootstrap_ui.Need(label="Something", pip=("something",))
        progress = bootstrap_ui.Progress(needs=[need])
        with patch.object(sys, "frozen", True, create=True), \
                patch.object(bootstrap_ui, "_run", side_effect=AssertionError("must not run")):
            self.assertFalse(bootstrap_ui._fetch(progress, need))

    def test_the_executable_does_not_ask_for_python_bindings(self):
        """PyGObject is built in; only the external programs remain to be checked."""
        spec = importlib.util.spec_from_file_location("run_frozen", str(ROOT / "run.py"))
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertNotIn("gi", [need.module for need in module.NEEDS])
        self.assertIn("wmctrl", [need.command for need in module.NEEDS])

    def test_the_autostart_never_names_the_interpreter(self):
        """In the executable sys.executable is the program, which needs no script."""
        content = autostart._desktop_entry_content()
        self.assertEqual(content.count(str(self.executable.resolve())), 1)
        self.assertNotIn("python", content.lower())


class TestMigration(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        base = Path(self._tmpdir.name)
        self.old = base / "checkout" / "entries.json"
        self.new = base / "config" / "startup-launcher" / "entries.json"
        self.old.parent.mkdir()

    def test_the_old_file_is_copied_when_the_new_one_is_missing(self):
        self.old.write_text("[]", encoding="utf-8")
        paths.migrate_legacy_user_data(((self.old, self.new),))
        self.assertEqual(self.new.read_text(encoding="utf-8"), "[]")
        self.assertTrue(self.old.is_file())

    def test_an_existing_new_file_is_never_overwritten(self):
        self.old.write_text("old", encoding="utf-8")
        self.new.parent.mkdir(parents=True)
        self.new.write_text("new", encoding="utf-8")
        paths.migrate_legacy_user_data(((self.old, self.new),))
        self.assertEqual(self.new.read_text(encoding="utf-8"), "new")

    def test_nothing_to_migrate_creates_nothing(self):
        paths.migrate_legacy_user_data(((self.old, self.new),))
        self.assertFalse(self.new.exists())

    def test_the_executable_has_nothing_to_migrate(self):
        self.old.write_text("old", encoding="utf-8")
        with patch.object(paths, "IS_FROZEN", True):
            paths.migrate_legacy_user_data(((self.old, self.new),))
        self.assertFalse(self.new.exists())

    def test_every_user_file_has_a_way_out_of_the_project_root(self):
        moved = {new for _old, new in paths.LEGACY_USER_FILES}
        self.assertEqual(moved, {paths.ENTRIES_FILE, paths.GEOMETRY_FILE, paths.SETTINGS_FILE})
        for old, _new in paths.LEGACY_USER_FILES:
            self.assertEqual(old.parent, paths.PROJECT_ROOT)


class TestChildEnvironment(unittest.TestCase):
    def test_children_get_no_paths_into_the_unpacked_files(self):
        env = {
            "LD_LIBRARY_PATH": "/tmp/_MEIabc",
            "LD_LIBRARY_PATH_ORIG": "/opt/lib",
            "GI_TYPELIB_PATH": "/tmp/_MEIabc/gi_typelibs",
            "XDG_DATA_DIRS": "/tmp/_MEIabc/share:/usr/share",
            "_PYI_ARCHIVE_FILE": "/home/me/startup-launcher",
            "HOME": "/home/me",
        }
        with patch.object(paths, "IS_FROZEN", True), \
                patch.object(sys, "_MEIPASS", "/tmp/_MEIabc", create=True):
            self.assertEqual(paths.child_environment(env), {
                "LD_LIBRARY_PATH": "/opt/lib",
                "XDG_DATA_DIRS": "/usr/share",
                "HOME": "/home/me",
            })

    def test_without_an_original_the_library_path_is_dropped(self):
        with patch.object(paths, "IS_FROZEN", True), \
                patch.object(sys, "_MEIPASS", "/tmp/_MEIabc", create=True):
            self.assertNotIn("LD_LIBRARY_PATH",
                             paths.child_environment({"LD_LIBRARY_PATH": "/tmp/_MEIabc"}))

    def test_a_checkout_hands_its_environment_on_unchanged(self):
        env = {"LD_LIBRARY_PATH": "/x", "_PYI_X": "y"}
        self.assertEqual(paths.child_environment(env), env)

    def test_every_popen_gets_the_clean_environment(self):
        with patch.object(subprocess, "Popen", subprocess.Popen), \
                patch.object(paths, "IS_FROZEN", True), \
                patch.object(sys, "_MEIPASS", "/tmp/_MEIabc", create=True), \
                patch.dict("os.environ", {"STARTUP_LAUNCHER_PROBE": "/tmp/_MEIabc/lib"}):
            paths.use_system_environment_for_children()
            paths.use_system_environment_for_children()
            output = subprocess.run(
                [sys.executable, "-c", "import os; print(os.environ.get('STARTUP_LAUNCHER_PROBE'))"],
                stdout=subprocess.PIPE, check=True,
            ).stdout.decode().strip()
            self.assertEqual(output, "None")
            self.assertFalse(getattr(subprocess.Popen.__bases__[0], "_startup_launcher_clean_env", False),
                             "patched only once")

    def test_a_launched_entry_starts_without_the_bundled_libraries(self):
        """The user's own programs are what this application starts most."""
        with tempfile.TemporaryDirectory() as base, \
                patch.object(subprocess, "Popen", subprocess.Popen), \
                patch.object(paths, "IS_FROZEN", True), \
                patch.object(sys, "_MEIPASS", "/tmp/_MEIabc", create=True), \
                patch.dict("os.environ", {"LD_LIBRARY_PATH": "/tmp/_MEIabc",
                                          "LD_LIBRARY_PATH_ORIG": "/opt/lib",
                                          "GI_TYPELIB_PATH": "/tmp/_MEIabc/gi_typelibs"}):
            paths.use_system_environment_for_children()
            out = Path(base) / "env.txt"
            entry = {
                "id": "e1", "name": "Probe", "window_mode": "normal", "match_mode": "class",
                "match_string": "", "delay_seconds": 0, "enabled": True,
                "command": f"sh -c 'echo \"$LD_LIBRARY_PATH|$GI_TYPELIB_PATH\" > {out}'",
            }
            launcher.launch_entry(entry)
            deadline = time.monotonic() + 5
            while not (out.is_file() and out.read_text(encoding="utf-8")) and time.monotonic() < deadline:
                time.sleep(0.05)
            self.assertEqual(out.read_text(encoding="utf-8").strip(), "/opt/lib|")


class TestBuildScript(unittest.TestCase):
    def test_the_build_installs_only_pyinstaller(self):
        packages = _build_script().bundled_packages()
        self.assertEqual(len(packages), 1)
        self.assertTrue(packages[0].startswith("pyinstaller"))

    def test_the_spec_file_compiles_limits_gtk_and_carries_the_data(self):
        build = _build_script()
        text = build.spec_text(Path("/tmp/stage"))
        compile(text, "startup-launcher.spec", "exec")
        self.assertIn("'icons': []", text)
        self.assertIn("'themes': []", text)
        self.assertIn("'Gtk': '3.0'", text)
        self.assertIn("console=False", text)
        self.assertIn("name={0!r}".format(paths.executable_name()), text)
        self.assertIn("('/tmp/stage', '.')", text)
        self.assertIn(repr(str(ROOT / "run.py")), text)

    def test_every_data_file_exists_and_the_examples_travel_along(self):
        files = _build_script().DATA_FILES
        self.assertIn(Path("entries.example.json"), files)
        for relative in files:
            self.assertTrue((ROOT / relative).is_file(), relative)

    def test_build_output_is_not_checked_in(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn("/build/", lines)
        self.assertIn("/dist/", lines)

    def test_the_workflow_tags_releases_with_version_and_build(self):
        workflow = (ROOT / ".github" / "workflows" / "release-exe.yml").read_text(encoding="utf-8")
        self.assertIn('TAG="v${VERSION}-build${BUILD}"', workflow)
        self.assertIn("fetch-depth: 0", workflow)
        self.assertIn("ubuntu-22.04", workflow)
        self.assertNotIn("windows", workflow)


if __name__ == "__main__":
    unittest.main()
