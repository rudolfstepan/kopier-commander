"""Copy engine tests using temporary directories only."""
from dataclasses import asdict
import hashlib
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from kopier_commander import core
from kopier_commander.core import CopyItem, compare_directories, copy_item, load_task, save_task


class CopyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.source = self.base / "quelle"
        self.target = self.base / "ziel"
        self.source.mkdir()
        self.target.mkdir()
        self.cancel = threading.Event()

    def tearDown(self):
        self.temporary.cleanup()

    def make_item(self, name="Film äöü.mkv", payload=b"0123456789" * 1000):
        source = self.source / name
        source.parent.mkdir(parents=True, exist_ok=True)
        source.write_bytes(payload)
        return CopyItem(str(source), str(self.target / name))

    def assert_no_temporary(self):
        self.assertEqual(list(self.target.rglob("*.part")), [])

    def test_verified_copy_and_restart_skip(self):
        item = self.make_item("Unterordner/Film äöü.mkv")
        self.assertEqual(copy_item(item, self.cancel), "copied")
        self.assertEqual(Path(item.source).read_bytes(), Path(item.destination).read_bytes())
        self.assertEqual(item.sha256, hashlib.sha256(Path(item.source).read_bytes()).hexdigest())
        self.assertTrue(item.copied_at)
        with patch.object(core.tempfile, "mkstemp", side_effect=AssertionError("Unnötige Wiederholung")):
            self.assertEqual(copy_item(item, self.cancel), "copied")
        self.assert_no_temporary()

    def test_existing_file_not_overwritten_or_marked_copied(self):
        item = self.make_item()
        Path(item.destination).write_bytes(b"BEHALTEN")
        self.assertEqual(copy_item(item, self.cancel), "exists")
        self.assertEqual(Path(item.destination).read_bytes(), b"BEHALTEN")
        self.assertFalse(item.copied_at)

    def test_explicit_overwrite(self):
        item = self.make_item()
        Path(item.destination).write_bytes(b"ALT")
        self.assertEqual(copy_item(item, self.cancel, overwrite=True), "copied")
        self.assertEqual(Path(item.destination).read_bytes(), Path(item.source).read_bytes())

    def test_changed_success_is_not_trusted(self):
        item = self.make_item()
        copy_item(item, self.cancel)
        Path(item.destination).write_bytes(b"veraendert")
        self.assertEqual(copy_item(item, self.cancel), "exists")
        self.assertEqual(Path(item.destination).read_bytes(), b"veraendert")

    def test_cancel_mid_copy_cleans_partial_and_preserves_old_destination(self):
        item = self.make_item(payload=b"abc" * 100)
        Path(item.destination).write_bytes(b"ALT")

        def progress(phase, done, total):
            if done > 0:
                self.cancel.set()

        with patch.object(core, "CHUNK_SIZE", 8):
            self.assertEqual(copy_item(item, self.cancel, overwrite=True, progress=progress), "cancelled")
        self.assertEqual(Path(item.destination).read_bytes(), b"ALT")
        self.assert_no_temporary()

    def test_source_change_during_copy_is_rejected(self):
        item = self.make_item(payload=b"0123456789" * 100)

        def progress(phase, done, total):
            if done == 0:
                Path(item.source).write_bytes(b"geaendert")

        self.assertEqual(copy_item(item, self.cancel, progress=progress), "error")
        self.assertIn("verändert", item.error)
        self.assertFalse(Path(item.destination).exists())
        self.assert_no_temporary()

    def test_checksum_mismatch_never_publishes(self):
        item = self.make_item()
        real_hash = hashlib.sha256
        calls = 0

        def factory():
            nonlocal calls
            calls += 1
            digest = real_hash()
            if calls == 2:
                digest.update(b"absichtlich verschieden")
            return digest

        with patch.object(core.hashlib, "sha256", side_effect=factory):
            self.assertEqual(copy_item(item, self.cancel), "error")
        self.assertIn("SHA-256", item.error)
        self.assertFalse(Path(item.destination).exists())
        self.assert_no_temporary()

    def test_destination_created_during_copy_is_preserved(self):
        item = self.make_item()

        def progress(phase, done, total):
            if phase == "verifying":
                Path(item.destination).write_bytes(b"NEUE FREMDDATEI")

        self.assertEqual(copy_item(item, self.cancel, progress=progress), "error")
        self.assertEqual(Path(item.destination).read_bytes(), b"NEUE FREMDDATEI")
        self.assert_no_temporary()

    def test_same_source_target_rejected(self):
        item = self.make_item()
        item.destination = item.source
        self.assertEqual(copy_item(item, self.cancel, overwrite=True), "error")
        self.assertEqual(Path(item.source).stat().st_size, 10000)

    def test_missing_source_reports_error(self):
        item = CopyItem(str(self.source / "fehlt"), str(self.target / "fehlt"))
        self.assertEqual(copy_item(item, self.cancel), "error")
        self.assertTrue(item.error)

    def test_recursive_comparison_and_relative_destination(self):
        self.make_item("gleich.mkv", b"abc")
        self.make_item("anders.mkv", b"abc")
        self.make_item("Serie/fehlt.mkv", b"xyz")
        (self.target / "gleich.mkv").write_bytes(b"abc")
        (self.target / "anders.mkv").write_bytes(b"ab")
        rows = compare_directories(str(self.source), str(self.target), self.cancel)
        states = {Path(row["name"]).as_posix(): row["comparison"] for row in rows}
        self.assertEqual(states, {"gleich.mkv": "equal", "anders.mkv": "different", "Serie/fehlt.mkv": "missing"})
        missing = next(row for row in rows if row["comparison"] == "missing")
        self.assertEqual(Path(missing["destination"]), self.target / "Serie" / "fehlt.mkv")

    def test_failed_compare_does_not_report_everything_missing(self):
        with self.assertRaises(OSError):
            compare_directories(str(self.source), str(self.base / "offline"), self.cancel)

    def test_task_roundtrip_and_interrupted_state_reset(self):
        item = self.make_item()
        copy_item(item, self.cancel)
        second = self.make_item("weiter.mkv")
        second.status = "verifying"
        task = self.base / "Aufgabe ü.json"
        save_task(task, [item, second], str(self.source), str(self.target))
        loaded, data = load_task(task)
        self.assertEqual(asdict(loaded[0]), asdict(item))
        self.assertEqual(loaded[1].status, "pending")
        self.assertTrue(data["verify"])
        self.assertFalse(data["overwrite"])

    def test_duplicate_targets_in_saved_task_rejected(self):
        first = self.make_item("eins")
        second = self.make_item("zwei")
        second.destination = first.destination
        task = self.base / "bad.json"
        save_task(task, [first, second], str(self.source), str(self.target))
        with self.assertRaises(ValueError):
            load_task(task)

    def test_atomic_save_preserves_previous_task_on_failure(self):
        task = self.base / "aufgabe.json"
        save_task(task, [], str(self.source), str(self.target))
        before = task.read_bytes()
        with patch.object(core.os, "replace", side_effect=OSError("Schreibfehler")):
            with self.assertRaises(OSError):
                save_task(task, [self.make_item()], str(self.source), str(self.target))
        self.assertEqual(task.read_bytes(), before)
        self.assertEqual(list(self.base.glob(".aufgabe-*.tmp")), [])


if __name__ == "__main__":
    unittest.main()
