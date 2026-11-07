"""Command-line launcher; help and version do not require a desktop or Tk."""
import argparse
import os
from pathlib import Path
import sys

from . import __version__


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kopier Commander – Dateikopien mit zwei Fenstern und Tastaturbedienung.")
    parser.add_argument("--version", action="version", version=f"Kopier Commander {__version__}")
    parser.add_argument("--source", metavar="ORDNER", help="Quellverzeichnis; startet eine neue leere Aufgabe")
    parser.add_argument("--target", metavar="ORDNER", help="Zielverzeichnis; startet eine neue leere Aufgabe")
    parser.add_argument("--task", type=Path, metavar="JSON", help="Eine gespeicherte Aufgabe laden")
    parser.add_argument("--data-dir", type=Path, metavar="ORDNER", help="Verzeichnis für die automatische Sicherung")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    if args.task is not None and (args.source is not None or args.target is not None):
        parser.error("--task kann nicht mit --source oder --target kombiniert werden.")
    if args.task is not None and not args.task.is_file():
        parser.error(f"Aufgabenfile nicht gefunden: {args.task}")
    if args.data_dir is not None:
        os.environ["KOPIER_COMMANDER_DATA_DIR"] = str(args.data_dir.expanduser().resolve())
    try:
        import tkinter as tk
        from .app import Commander
    except ImportError as error:
        print(f"Tkinter wird benötigt: {error}\nBitte Python mit Tcl/Tk-Unterstützung installieren.", file=sys.stderr)
        return 1
    window = None
    try:
        window = tk.Tk()
        Commander(window, source=args.source, target=args.target,
                  task=args.task.resolve() if args.task is not None else None)
        window.mainloop()
    except Exception as error:
        print(f"Kopier Commander konnte nicht gestartet werden: {error}", file=sys.stderr)
        if window is not None:
            from tkinter import messagebox
            messagebox.showerror("Kopier Commander", str(error), parent=window)
            window.destroy()
        return 1
    return 0
