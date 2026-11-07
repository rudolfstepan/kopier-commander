"""Copy engine and portable JSON tasks; uses only the Python standard library."""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import stat
import tempfile
import threading
import time
from typing import Callable

DEFAULT_SOURCE = str(Path.home())
DEFAULT_DESTINATION = str(Path.home())
CHUNK_SIZE = 4 * 1024 * 1024
STATUSES = {"pending", "copying", "verifying", "copied", "exists", "error", "cancelled"}
LABELS = {
    "pending": "Bereit", "copying": "Kopiert …", "verifying": "Prüft SHA-256 …",
    "copied": "✓ Kopiert", "exists": "Ziel vorhanden – übersprungen",
    "error": "Fehler", "cancelled": "Abgebrochen",
}


def path_key(path: str | Path) -> str:
    return os.path.normcase(os.path.abspath(path))


def human_size(size: float) -> str:
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if abs(size) < 1024 or unit == "TiB":
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024
    return ""


@dataclass
class CopyItem:
    source: str
    destination: str
    size: int = 0
    mtime_ns: int = 0
    status: str = "pending"
    error: str = ""
    sha256: str = ""
    copied_at: str = ""
    target_mtime_ns: int = 0


def save_task(path: str | Path, items: list[CopyItem], source: str,
              destination: str, overwrite: bool = False, verify: bool = True) -> None:
    """Atomic write, so an interrupted save cannot truncate the last good task."""
    path = Path(path)
    payload = {"format": "kopier-commander", "version": 1,
               "source_directory": source, "destination_directory": destination,
               "overwrite": overwrite, "verify": verify,
               "items": [asdict(item) for item in items]}
    fd, temporary = tempfile.mkstemp(prefix=".aufgabe-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def load_task(path: str | Path) -> tuple[list[CopyItem], dict]:
    with open(path, encoding="utf-8-sig") as handle:
        data = json.load(handle)
    if not isinstance(data, dict) or data.get("format") != "kopier-commander" or data.get("version") != 1:
        raise ValueError("Keine unterstützte Kopier-Commander-Aufgabe (Version 1).")
    if not isinstance(data.get("items"), list):
        raise ValueError("Die Dateiliste fehlt.")
    for name in ("source_directory", "destination_directory"):
        if not isinstance(data.get(name), str) or not os.path.isabs(data[name]):
            raise ValueError(f"Ungültiger Verzeichnispfad: {name}")
    for name in ("overwrite", "verify"):
        if name in data and not isinstance(data[name], bool):
            raise ValueError(f"Ungültige Einstellung: {name}")
    result, seen_sources, seen_targets = [], set(), set()
    allowed = {field.name for field in fields(CopyItem)}
    for row in data["items"]:
        if not isinstance(row, dict):
            raise ValueError("Ungültiger Dateieintrag.")
        for name in ("source", "destination"):
            if not isinstance(row.get(name), str) or not os.path.isabs(row[name]) or "\x00" in row[name]:
                raise ValueError(f"Ungültiger Dateipfad: {name}")
        item = CopyItem(**{key: value for key, value in row.items() if key in allowed})
        if item.status not in STATUSES:
            raise ValueError("Unbekannter Kopierstatus.")
        for name in ("size", "mtime_ns", "target_mtime_ns"):
            if not isinstance(getattr(item, name), int) or getattr(item, name) < 0:
                raise ValueError(f"Ungültige Dateiinformation: {name}")
        for name in ("error", "sha256", "copied_at"):
            if not isinstance(getattr(item, name), str):
                raise ValueError(f"Ungültige Dateiinformation: {name}")
        source_key, target_key = path_key(item.source), path_key(item.destination)
        if source_key in seen_sources or target_key in seen_targets:
            raise ValueError("Die Aufgabe enthält doppelte Quell- oder Zieldateien.")
        seen_sources.add(source_key)
        seen_targets.add(target_key)
        if item.status in {"copying", "verifying", "cancelled"}:
            item.status = "pending"
            item.error = ""
        result.append(item)
    return result, data


class CopyCancelled(Exception):
    pass


def compare_directories(source: str, destination: str, cancel: threading.Event,
                        progress: Callable[[int], None] | None = None) -> list[dict]:
    """Compare relative filenames and sizes, including subdirectories (not contents)."""
    rows = []
    last_report = 0.0

    def walk_error(error: OSError) -> None:
        raise error

    if not stat.S_ISDIR(Path(source).stat().st_mode):
        raise OSError(f"Quellverzeichnis nicht erreichbar: {source}")
    if not stat.S_ISDIR(Path(destination).stat().st_mode):
        raise OSError(f"Zielverzeichnis nicht erreichbar: {destination}")
    for directory, folders, filenames in os.walk(source, onerror=walk_error, followlinks=False):
        if cancel.is_set():
            raise CopyCancelled()
        folders.sort(key=str.casefold)
        for name in sorted(filenames, key=str.casefold):
            if cancel.is_set():
                raise CopyCancelled()
            path = Path(directory) / name
            info = path.stat()
            relative = path.relative_to(source)
            target = Path(destination) / relative
            try:
                target_info = target.stat()
                state = "equal" if target.is_file() and target_info.st_size == info.st_size else "different"
            except FileNotFoundError:
                state = "missing"
            rows.append({"path": str(path), "name": str(relative), "size": info.st_size,
                         "mtime_ns": info.st_mtime_ns, "is_dir": False,
                         "destination": str(target), "comparison": state})
            now = time.monotonic()
            if progress and now - last_report > 0.25:
                progress(len(rows))
                last_report = now
    return rows


def copy_item(item: CopyItem, cancel: threading.Event, overwrite: bool = False,
              verify: bool = True, progress: Callable[[str, int, int], None] | None = None) -> str:
    """Copy via a unique temporary file; publish only a complete, checked result.

    Progress callbacks execute on the calling worker thread, never on the GUI.
    Existing files are never reported as successful copies of this task.
    """
    temporary = None
    source, destination = Path(item.source), Path(item.destination)
    last_report = 0.0

    def report(phase: str, done: int, total: int, force: bool = False) -> None:
        nonlocal last_report
        if cancel.is_set():
            raise CopyCancelled()
        now = time.monotonic()
        if progress and (force or now - last_report >= 0.15):
            progress(phase, done, total)
            last_report = now
        if cancel.is_set():
            raise CopyCancelled()

    try:
        if cancel.is_set():
            raise CopyCancelled()
        if path_key(source) == path_key(destination):
            raise ValueError("Quelle und Ziel sind dieselbe Datei.")
        initial = source.stat()
        if not source.is_file():
            raise ValueError("Die Quelle ist keine reguläre Datei.")
        if destination.exists() and os.path.samefile(source, destination):
            raise ValueError("Quelle und Ziel verweisen auf dieselbe Datei.")
        # A completed task can be continued without copying its unchanged successes again.
        if item.status == "copied" and destination.is_file():
            target_stat = destination.stat()
            if (item.size == initial.st_size == target_stat.st_size
                    and item.mtime_ns == initial.st_mtime_ns
                    and item.target_mtime_ns == target_stat.st_mtime_ns
                    and (not verify or item.sha256)):
                item.error = ""
                return "copied"
        item.size, item.mtime_ns = initial.st_size, initial.st_mtime_ns
        item.sha256 = item.copied_at = item.error = ""
        item.target_mtime_ns = 0
        if destination.exists() and not overwrite:
            item.status = "exists"
            return item.status
        destination.parent.mkdir(parents=True, exist_ok=True)
        item.status = "copying"
        digest = hashlib.sha256() if verify else None
        copied = 0
        report("copying", 0, item.size, True)
        fd, temporary = tempfile.mkstemp(prefix=".kopier-", suffix=".part", dir=destination.parent)
        with os.fdopen(fd, "wb") as output, source.open("rb") as input_file:
            while True:
                report("copying", copied, item.size)
                chunk = input_file.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
                if digest is not None:
                    digest.update(chunk)
                copied += len(chunk)
            final_open = os.fstat(input_file.fileno())
            output.flush()
            os.fsync(output.fileno())
        final_path = source.stat()
        if (copied != item.size or final_open.st_size != initial.st_size
                or final_open.st_mtime_ns != initial.st_mtime_ns
                or final_path.st_size != initial.st_size
                or final_path.st_mtime_ns != initial.st_mtime_ns):
            raise OSError("Die Quelldatei wurde während des Kopierens verändert.")
        if digest is not None:
            item.status = "verifying"
            report("verifying", 0, item.size, True)
            target_digest, checked = hashlib.sha256(), 0
            with open(temporary, "rb") as copied_file:
                while True:
                    report("verifying", checked, item.size)
                    chunk = copied_file.read(CHUNK_SIZE)
                    if not chunk:
                        break
                    target_digest.update(chunk)
                    checked += len(chunk)
            if checked != item.size or target_digest.digest() != digest.digest():
                raise OSError("SHA-256-Prüfung fehlgeschlagen; Kopie wird verworfen.")
            item.sha256 = digest.hexdigest()
        os.utime(temporary, ns=(initial.st_atime_ns, initial.st_mtime_ns))
        # Obtain metadata before publication, so no post-publication I/O can turn success into failure.
        target_mtime_ns = os.stat(temporary).st_mtime_ns
        report(item.status, item.size, item.size, True)
        if overwrite:
            os.replace(temporary, destination)
        elif os.name == "nt":
            os.rename(temporary, destination)  # Windows rename refuses an existing target.
        else:
            os.link(temporary, destination)  # Atomic no-replace publication on POSIX.
            os.unlink(temporary)
        temporary = None
        item.target_mtime_ns = target_mtime_ns
        item.copied_at = datetime.now().isoformat(timespec="seconds")
        item.status = "copied"
    except CopyCancelled:
        item.status, item.error = "cancelled", "Vom Benutzer abgebrochen."
    except Exception as error:
        item.status, item.error = "error", str(error)
    finally:
        if temporary:
            try:
                os.unlink(temporary)
            except OSError as error:
                item.error += f" Temporäre Datei konnte nicht entfernt werden: {temporary}: {error}"
    return item.status
