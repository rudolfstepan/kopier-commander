"""Real Tk integration test with temporary directories; never copies the film library."""
from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from unittest.mock import patch

from kopier_commander import app
from kopier_commander.core import load_task, path_key


class GuiTests(unittest.TestCase):
    def test_keyboard_compare_select_copy_save_restore(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            source, target = base / "quelle", base / "ziel"
            source.mkdir()
            target.mkdir()
            (source / "gleich.mkv").write_bytes(b"gleich")
            (target / "gleich.mkv").write_bytes(b"gleich")
            (source / "fehlt.mkv").write_bytes(b"neuer Film" * 1024)
            (source / "Unterordner").mkdir()
            (source / "Unterordner" / "auch neu.mkv").write_bytes(b"Unterordnerfilm")
            with (patch.object(app, "DEFAULT_SOURCE", str(source)),
                  patch.object(app, "DEFAULT_DESTINATION", str(target)),
                  patch.object(app, "HOME", base), patch.object(app, "AUTOSAVE", base / "auto.json")):
                root = tk.Tk()
                callback_errors = []
                root.report_callback_exception = lambda *error: callback_errors.append(error)
                try:
                    ui = app.Commander(root)

                    def wait_until(condition, timeout=10):
                        deadline = time.monotonic() + timeout
                        while not condition():
                            root.update()
                            if callback_errors:
                                raise AssertionError(callback_errors)
                            if time.monotonic() > deadline:
                                raise AssertionError("GUI timeout: " + ui.status.get())
                            time.sleep(0.01)
                        root.update()
                        self.assertEqual(callback_errors, [])

                    wait_until(lambda: len(ui.source.rows) == 3 and len(ui.target.rows) == 1)
                    root.geometry("1000x760")
                    root.update()
                    for button in ui.action_buttons.values():
                        self.assertLessEqual(button.winfo_rootx() + button.winfo_width(),
                                             root.winfo_rootx() + root.winfo_width())
                        self.assertLessEqual(button.winfo_rooty() + button.winfo_height(),
                                             root.winfo_rooty() + root.winfo_height())
                    root.focus_force()
                    ui.source.focus_files()
                    root.update()
                    iid = next(iid for iid, row in ui.source.displayed.items() if row["name"] == "fehlt.mkv")
                    ui.source.tree.focus(iid)
                    ui.source.tree.selection_set(iid)
                    ui.source.tree.event_generate("<space>")
                    root.update()
                    self.assertIn(path_key(source / "fehlt.mkv"), ui.items)
                    ui.source.tree.event_generate("<Tab>")
                    root.update()
                    self.assertEqual(root.focus_get(), ui.target.tree)
                    root.event_generate("<F3>")
                    wait_until(lambda: not ui.comparing and ui.source.comparison_mode)
                    self.assertEqual(sum(row["comparison"] == "missing" for row in ui.source.rows), 2)
                    root.event_generate("<Shift-F3>")
                    root.update()
                    self.assertEqual(len(ui.items), 2)
                    root.event_generate("<Alt-m>")
                    root.update()
                    self.assertTrue(ui.source.only_missing.get())
                    self.assertEqual(len(ui.source.displayed), 2)
                    root.event_generate("<F5>")
                    wait_until(lambda: not ui.running and all(item.status == "copied" for item in ui.items.values()))
                    self.assertEqual((target / "fehlt.mkv").read_bytes(), (source / "fehlt.mkv").read_bytes())
                    self.assertEqual((target / "Unterordner" / "auch neu.mkv").read_bytes(), b"Unterordnerfilm")
                    self.assertEqual(len(ui.source.displayed), 0)
                    self.assertTrue(ui.persist())
                    restored, _ = load_task(base / "auto.json")
                    self.assertEqual(len(restored), 2)
                    self.assertTrue(all(item.status == "copied" and item.sha256 for item in restored))
                    self.assertEqual(callback_errors, [])
                finally:
                    root.destroy()


if __name__ == "__main__":
    unittest.main()
