"""Keyboard-friendly, Norton Commander-inspired NAS copy application."""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, replace
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import (CopyCancelled, CopyItem, DEFAULT_DESTINATION, DEFAULT_SOURCE,
                  LABELS, compare_directories, copy_item, human_size, load_task,
                  path_key, save_task)

from .config import data_directory

HOME = data_directory()
AUTOSAVE = HOME / "letzte-aufgabe.json"
BLUE, DARK, CYAN, YELLOW = "#000080", "#000050", "#55ffff", "#ffff55"
WHITE, GREEN, RED = "#eeeeee", "#55ff99", "#ff8888"
COMPARE_LABELS = {"missing": "Fehlt im Ziel", "different": "Andere Größe / Typ",
                  "equal": "Vorhanden · Größe gleich"}


class FilePane(ttk.Frame):
    def __init__(self, app: "Commander", source: bool):
        super().__init__(app.panes, style="Panel.TFrame", padding=3)
        self.app, self.source = app, source
        self.current = DEFAULT_SOURCE if source else DEFAULT_DESTINATION
        self.rows: list[dict] = []
        self.displayed: dict[str, dict] = {}
        self.generation = 0
        self.comparison_mode = False
        self.filter_after = None
        title = " QUELLE · NAS · Checkbox = Kopierauswahl " if source else " ZIEL · Lokale Dateien "
        ttk.Label(self, text=title, style="Title.TLabel").pack(fill="x")
        path_bar = ttk.Frame(self)
        path_bar.pack(fill="x", pady=(4, 3))
        self.path = tk.StringVar(value=self.current)
        self.entry = ttk.Entry(path_bar, textvariable=self.path)
        self.entry.pack(side="left", fill="x", expand=True)
        self.entry.bind("<Return>", lambda event: self.navigate(self.path.get()))
        self.entry.bind("<Escape>", lambda event: self.focus_files())
        ttk.Button(path_bar, text="↑", width=3, command=self.parent).pack(side="left", padx=2)
        self.browse_button = ttk.Button(path_bar, text="…", width=3, command=self.browse)
        self.browse_button.pack(side="left")
        filter_bar = ttk.Frame(self)
        filter_bar.pack(fill="x", pady=(0, 3))
        ttk.Label(filter_bar, text="Filter:").pack(side="left")
        self.filter = tk.StringVar()
        self.filter_entry = ttk.Entry(filter_bar, textvariable=self.filter)
        self.filter_entry.pack(side="left", fill="x", expand=True, padx=4)
        self.filter.trace_add("write", self.filter_changed)
        self.filter_entry.bind("<Return>", lambda event: self.focus_files())
        self.filter_entry.bind("<Escape>", self.clear_filter)
        self.only_missing = tk.BooleanVar()
        if source:
            ttk.Checkbutton(filter_bar, text="Nur fehlende", variable=self.only_missing,
                            command=self.render).pack(side="left")
        body = ttk.Frame(self)
        body.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(body, columns=("name", "size", "state"), show="tree headings",
                                 selectmode="extended", style="Commander.Treeview")
        self.tree.heading("#0", text="☑" if source else "")
        self.tree.column("#0", width=34, minwidth=34, stretch=False)
        for column, text, width in (("name", "Dateiname", 300), ("size", "Größe", 105),
                                    ("state", "Status", 205)):
            self.tree.heading(column, text=text, command=lambda col=column: self.sort(col))
            self.tree.column(column, width=width, minwidth=65, anchor="e" if column == "size" else "w")
        vertical = ttk.Scrollbar(body, orient="vertical", command=self.tree.yview)
        horizontal = ttk.Scrollbar(body, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        for tag, color in (("copied", GREEN), ("missing", YELLOW), ("different", RED),
                           ("error", RED), ("selected", YELLOW), ("folder", CYAN)):
            self.tree.tag_configure(tag, foreground=color)
        self.summary = tk.StringVar(value="Verzeichnis wird gelesen …")
        ttk.Label(self, textvariable=self.summary).pack(fill="x", pady=3)
        self.tree.bind("<Button-1>", self.click)
        self.tree.bind("<Double-1>", self.double_click)
        self.tree.bind("<Return>", self.enter)
        self.tree.bind("<BackSpace>", lambda event: self.parent())
        self.tree.bind("<Control-l>", lambda event: self.focus_path())
        self.tree.bind("<Tab>", lambda event: self.app.other_pane(self).focus_files())
        self.tree.bind("<Shift-Tab>", lambda event: self.app.other_pane(self).focus_files())
        self.tree.bind("<FocusIn>", lambda event: self.app.set_active(self))
        if source:
            self.tree.bind("<space>", self.toggle_key)
            self.tree.bind("<Insert>", self.toggle_key)
            self.tree.bind("<Control-a>", lambda event: self.mark_all(True))
            self.tree.bind("<Control-Shift-A>", lambda event: self.mark_all(False))
            self.tree.bind("<Control-i>", lambda event: self.mark_all(None))

    def focus_files(self):
        self.tree.focus_set()
        if not self.tree.focus() and self.tree.get_children():
            first = self.tree.get_children()[0]
            self.tree.focus(first)
            self.tree.selection_set(first)
        return "break"

    def focus_path(self):
        self.entry.focus_set()
        self.entry.selection_range(0, "end")
        return "break"

    def clear_filter(self, event=None):
        self.filter.set("")
        return self.focus_files()

    def filter_changed(self, *args):
        if self.filter_after:
            self.after_cancel(self.filter_after)
        self.filter_after = self.after(120, self.render)

    def browse(self):
        directory = filedialog.askdirectory(parent=self.app.root, initialdir=self.current,
                                             title="Quelle wählen" if self.source else "Ziel wählen")
        if directory:
            self.navigate(directory)

    def parent(self):
        self.navigate(str(Path(self.current).parent))
        return "break"

    def navigate(self, directory: str):
        if self.app.running or self.app.comparing:
            self.app.status.set("Navigation nach Abschluss oder Abbruch wieder verfügbar.")
            return "break"
        directory = os.path.abspath(os.path.expanduser(directory.strip().strip('"')))
        self.generation += 1
        generation = self.generation
        self.summary.set("Lese " + directory + " …")

        def worker():
            try:
                rows = []
                with os.scandir(directory) as iterator:
                    for entry in iterator:
                        is_dir = entry.is_dir(follow_symlinks=False)
                        stat = entry.stat()
                        rows.append({"path": entry.path, "name": entry.name,
                                     "size": stat.st_size, "mtime_ns": stat.st_mtime_ns,
                                     "is_dir": is_dir})
                rows.sort(key=lambda row: (not row["is_dir"], row["name"].casefold()))
                self.app.events.put(("scan", self.source, generation, directory, rows, ""))
            except Exception as error:
                self.app.events.put(("scan", self.source, generation, directory, [], str(error)))
        threading.Thread(target=worker, daemon=True).start()
        return "break"

    def accept_scan(self, generation, directory, rows, error):
        if generation != self.generation:
            return
        if error:
            self.path.set(self.current)
            self.summary.set("Lesefehler: " + error)
            self.app.status.set("Verzeichnis nicht erreichbar: " + error)
            return
        self.current = directory
        self.path.set(directory)
        self.rows, self.comparison_mode = rows, False
        if not self.source and self.app.source.comparison_mode:
            self.app.source.rows = [dict(row, comparison="", destination="") for row in self.app.source.rows]
            self.app.source.comparison_mode = False
            self.app.source.navigate(self.app.source.current)
        self.render()
        if not self.source:
            self.app.source.render()

    def state_for(self, row):
        if row["is_dir"]:
            return "<VERZEICHNIS>", "folder"
        item = self.app.items.get(path_key(row["path"])) if self.source else None
        if item:
            return LABELS[item.status], item.status if item.status in {"copied", "error"} else "selected"
        comparison = row.get("comparison")
        if comparison:
            return COMPARE_LABELS[comparison], comparison
        if self.source:
            target = self.app.target_files.get(row["name"])
            if target is not None:
                return ("Vorhanden · Größe gleich", "") if target == row["size"] else ("Andere Größe", "different")
        return "", ""

    def render(self):
        self.filter_after = None
        focus = self.displayed.get(self.tree.focus(), {}).get("path")
        self.tree.delete(*self.tree.get_children())
        self.displayed.clear()
        if not self.source:
            self.app.target_files = {row["name"]: row["size"] for row in self.rows if not row["is_dir"]}
        query = self.filter.get().casefold()
        for index, row in enumerate(self.rows):
            if query and query not in row["name"].casefold():
                continue
            if self.source and self.only_missing.get():
                if row["is_dir"]:
                    continue
                if row.get("comparison") != "missing":
                    if row.get("comparison") or row["name"] in self.app.target_files:
                        continue
            iid = str(index)
            self.displayed[iid] = row
            state, tag = self.state_for(row)
            chosen = path_key(row["path"]) in self.app.items
            image = self.app.checked if chosen else self.app.unchecked
            options = {"image": image} if self.source and not row["is_dir"] else {}
            self.tree.insert("", "end", iid=iid,
                             values=(row["name"] + ("\\" if row["is_dir"] else ""),
                                     "<DIR>" if row["is_dir"] else human_size(row["size"]), state),
                             tags=(tag,) if tag else (), **options)
            if focus == row["path"]:
                self.tree.focus(iid)
                self.tree.selection_set(iid)
        files = [row for row in self.displayed.values() if not row["is_dir"]]
        self.summary.set(f"{len(files)} Dateien · {human_size(sum(row['size'] for row in files))}"
                         + (" · rekursiver Vergleich" if self.comparison_mode else ""))

    def sort(self, column):
        reverse = getattr(self, "sort_column", None) == column and not getattr(self, "reverse", False)
        self.sort_column, self.reverse = column, reverse
        key = ((lambda row: row["size"]) if column == "size" else
               (lambda row: self.state_for(row)[0]) if column == "state" else
               (lambda row: row["name"].casefold()))
        self.rows.sort(key=key, reverse=reverse)
        self.render()

    def click(self, event):
        if self.source and self.tree.identify_column(event.x) == "#0":
            iid = self.tree.identify_row(event.y)
            if iid:
                self.tree.focus_set()
                self.tree.focus(iid)
                self.tree.selection_set(iid)
                self.app.toggle(self.displayed[iid])
                return "break"

    def double_click(self, event):
        if self.tree.identify_column(event.x) != "#0":
            return self.enter()
        return "break"

    def enter(self, event=None):
        row = self.displayed.get(self.tree.focus())
        if row:
            if row["is_dir"]:
                self.navigate(row["path"])
            elif self.source:
                self.app.toggle(row)
        return "break"

    def toggle_key(self, event=None):
        iid = self.tree.focus()
        row = self.displayed.get(iid)
        if row and not row["is_dir"]:
            children = self.tree.get_children()
            next_index = min(children.index(iid) + 1, len(children) - 1)
            self.app.toggle(row)
            following = children[next_index]
            self.tree.focus(following)
            self.tree.selection_set(following)
            self.tree.see(following)
        return "break"

    def mark_all(self, mode):
        if not self.app.running and not self.app.comparing:
            for row in list(self.displayed.values()):
                if not row["is_dir"]:
                    selected = path_key(row["path"]) in self.app.items
                    if mode is None or selected != mode:
                        self.app.toggle(row, refresh=False)
            self.app.changed()
        return "break"


class Commander:
    def __init__(self, root: tk.Tk, *, source: str | None = None,
                 target: str | None = None, task: Path | None = None):
        self.root = root
        self.items: dict[str, CopyItem] = {}
        self.target_files = {}
        self.events = queue.Queue()
        self.running = self.comparing = self.closing = False
        self.cancel = threading.Event()
        self.compare_cancel = threading.Event()
        self.task_path: Path | None = None
        self.save_after = None
        self.completed_bytes = 0
        self.total_bytes = 0
        self.started_at = 0.0
        self.active_key = None
        self.style()
        root.title("Kopier Commander")
        assets = Path(__file__).resolve().parent / "assets"
        self.app_icons = [tk.PhotoImage(master=root, file=str(assets / f"kopier-commander-{size}.png"))
                          for size in (16, 32, 48, 256)]
        root.iconphoto(True, *self.app_icons)
        if os.name == "nt":
            root.iconbitmap(default=str(assets / "kopier-commander.ico"))
        root.geometry("1500x900")
        root.minsize(1000, 760)
        root.columnconfigure(0, weight=1)
        root.rowconfigure(1, weight=1)
        root.configure(bg=BLUE)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.checked, self.unchecked = self.checkbox(True), self.checkbox(False)
        self.status = tk.StringVar(value="Bereit · Tab wechselt die Fenster · Leertaste/Einfg markiert Dateien · F1 Hilfe")
        ttk.Label(root, text="═ KOPIER COMMANDER ═", style="Banner.TLabel").grid(row=0, column=0, sticky="ew")
        self.panes = ttk.Panedwindow(root, orient="horizontal")
        self.panes.grid(row=1, column=0, sticky="nsew", padx=8, pady=(4, 0))
        self.source, self.target = FilePane(self, True), FilePane(self, False)
        self.panes.add(self.source, weight=1)
        self.panes.add(self.target, weight=1)
        self.active_pane = self.source
        options = ttk.Frame(root, padding=(8, 5))
        options.grid(row=2, column=0, sticky="ew")
        self.overwrite = tk.BooleanVar(value=False)
        self.verify = tk.BooleanVar(value=True)
        self.overwrite_check = ttk.Checkbutton(options, text="Vorhandene Ziele überschreiben", variable=self.overwrite,
                                             command=self.schedule_save)
        self.overwrite_check.pack(side="left")
        self.verify_check = ttk.Checkbutton(options, text="Kopien mit SHA-256 prüfen", variable=self.verify,
                                          command=self.schedule_save)
        self.verify_check.pack(side="left", padx=18)
        self.missing_button = ttk.Button(options, text="Shift+F3  Fehlende markieren", command=self.mark_missing)
        self.missing_button.pack(side="right")
        self.task_title = tk.StringVar(value=" AUFGABE · Checkboxen links fügen Dateien mit ihrem Zielpfad hinzu ")
        ttk.Label(root, textvariable=self.task_title, style="Title.TLabel").grid(row=3, column=0, sticky="ew", padx=8)
        task_frame = ttk.Frame(root, padding=(8, 0))
        task_frame.grid(row=4, column=0, sticky="ew")
        self.task_tree = ttk.Treeview(task_frame, columns=("source", "target", "size", "status"),
                                      show="headings", height=5, style="Commander.Treeview")
        for column, name, width in (("source", "Quelldatei", 380), ("target", "Zieldatei", 420),
                                     ("size", "Größe", 100), ("status", "Ergebnis", 250)):
            self.task_tree.heading(column, text=name)
            self.task_tree.column(column, width=width, anchor="e" if column == "size" else "w")
        scroll = ttk.Scrollbar(task_frame, orient="vertical", command=self.task_tree.yview)
        self.task_tree.configure(yscrollcommand=scroll.set)
        self.task_tree.pack(side="left", fill="x", expand=True)
        scroll.pack(side="right", fill="y")
        for tag, color in (("copied", GREEN), ("error", RED), ("exists", YELLOW), ("cancelled", YELLOW)):
            self.task_tree.tag_configure(tag, foreground=color)
        self.task_tree.bind("<Delete>", self.remove_selected)
        self.task_tree.bind("<Control-a>", self.select_all_tasks)
        self.task_tree.bind("<Return>", self.details)
        self.task_tree.bind("<Double-1>", self.details)
        self.task_tree.bind("<Tab>", lambda event: self.source.focus_files())
        progress_frame = ttk.Frame(root, padding=(8, 5))
        progress_frame.grid(row=5, column=0, sticky="ew")
        self.progress_text = tk.StringVar(value="Keine Kopie gestartet. F3 vergleicht Namen und Größen rekursiv.")
        ttk.Label(progress_frame, textvariable=self.progress_text).pack(fill="x")
        self.file_progress = ttk.Progressbar(progress_frame, maximum=100)
        self.file_progress.pack(fill="x", pady=3)
        self.total_progress = ttk.Progressbar(progress_frame, maximum=100)
        self.total_progress.pack(fill="x")
        self.status_label = ttk.Label(root, textvariable=self.status, wraplength=1450)
        self.status_label.grid(row=6, column=0, sticky="ew", padx=8, pady=(0, 5))
        root.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(300, event.width - 24))
                  if event.widget == root else None, add="+")
        bar = ttk.Frame(root, style="Bar.TFrame", padding=4)
        bar.grid(row=7, column=0, sticky="ew")
        actions = [("F1 Hilfe", self.help), ("F2 Speichern", self.save_as),
                   ("⇧F2 Laden", self.load_dialog), ("F3 Prüfen", self.compare),
                   ("F4 Filter", self.focus_filter), ("F5 Kopieren", self.start_copy),
                   ("F6 Aufgabe", self.focus_task), ("F8 Entfernen", self.remove_selected),
                   ("F9 Aktualisieren", self.refresh), ("Esc Abbruch", self.abort), ("F10 Ende", self.close)]
        self.action_buttons = {}
        self.function_columns = len(actions)
        for index, (label, action) in enumerate(actions):
            button = ttk.Button(bar, text=label, command=action, style="Function.TButton")
            button.grid(row=0, column=index, sticky="ew", padx=1, pady=1)
            bar.columnconfigure(index, weight=1, uniform="function")
            self.action_buttons[label] = button
        bar.bind("<Configure>", lambda event: self.layout_functions(bar, event.width))
        bindings = {"<F1>": self.help, "<F2>": self.save_as, "<Shift-F2>": self.load_dialog,
                    "<F3>": self.compare, "<Shift-F3>": self.mark_missing,
                    "<F4>": self.focus_filter, "<F5>": self.start_copy, "<F6>": self.focus_task,
                    "<F8>": self.remove_selected, "<F9>": self.refresh, "<F10>": self.close,
                    "<Escape>": self.abort, "<Control-s>": self.save_as,
                    "<Control-o>": self.load_dialog, "<Alt-s>": self.source.focus_path,
                    "<Alt-z>": self.target.focus_path, "<Alt-m>": self.toggle_missing,
                    "<Alt-u>": self.toggle_overwrite, "<Alt-h>": self.toggle_verify}
        for sequence, action in bindings.items():
            root.bind(sequence, lambda event, command=action: self.shortcut(command))
        if task is not None:
            self.apply_task(task)
            self.task_path = task
            self.render_task()
        elif source is None and target is None:
            self.restore()
        if source is not None:
            self.source.current = os.path.abspath(os.path.expanduser(source))
        if target is not None:
            self.target.current = os.path.abspath(os.path.expanduser(target))
        self.source.navigate(self.source.current)
        self.target.navigate(self.target.current)
        self.source.focus_files()
        root.after(100, self.poll)

    def style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        font = ("Consolas", 11)
        style.configure(".", background=BLUE, foreground=WHITE, font=font)
        style.configure("TEntry", fieldbackground=DARK, foreground=WHITE, insertcolor=YELLOW,
                        bordercolor=CYAN, padding=4)
        style.configure("TButton", background=CYAN, foreground=BLUE, padding=4)
        style.map("TButton", background=[("active", YELLOW), ("disabled", "#666688")],
                  foreground=[("disabled", "#bbbbbb")])
        style.configure("Panel.TFrame", borderwidth=2, relief="ridge", bordercolor=CYAN)
        style.configure("Title.TLabel", background=CYAN, foreground=BLUE, font=("Consolas", 11, "bold"))
        style.configure("Banner.TLabel", background=BLUE, foreground=YELLOW,
                        anchor="center", font=("Consolas", 17, "bold"), padding=5)
        style.configure("Commander.Treeview", background=BLUE, fieldbackground=BLUE,
                        foreground=WHITE, rowheight=25, bordercolor=CYAN, font=font)
        style.configure("Commander.Treeview.Heading", background=BLUE, foreground=YELLOW,
                        font=("Consolas", 11, "bold"), relief="flat")
        style.map("Commander.Treeview", background=[("selected", "#008888")],
                  foreground=[("selected", YELLOW)])
        style.map("Commander.Treeview.Heading", background=[("active", "#004499")])
        style.configure("TCheckbutton", background=BLUE, foreground=WHITE)
        style.map("TCheckbutton", background=[("active", BLUE)])
        style.configure("TProgressbar", background=CYAN, troughcolor=DARK)
        style.configure("Bar.TFrame", background=DARK)
        style.configure("Function.TButton", background=CYAN, foreground=BLUE,
                        font=("Consolas", 10, "bold"), padding=(3, 8))

    def checkbox(self, selected):
        image = tk.PhotoImage(master=self.root, width=18, height=18)
        image.put(CYAN, to=(1, 1, 17, 17))
        image.put(BLUE, to=(3, 3, 15, 15))
        if selected:
            for x, y in ((4, 8), (5, 9), (6, 10), (7, 11), (8, 10), (9, 9), (10, 8), (11, 7), (12, 6)):
                image.put(YELLOW, to=(x, y, x + 2, y + 2))
        return image

    def layout_functions(self, bar, width):
        buttons = list(self.action_buttons.values())
        requested = max(button.winfo_reqwidth() + 2 for button in buttons) * len(buttons) + 8
        columns = len(buttons) if width >= requested else 6
        if columns == self.function_columns:
            return
        self.function_columns = columns
        for index in range(len(buttons)):
            bar.columnconfigure(index, weight=1 if index < columns else 0,
                                uniform="function" if index < columns else "")
            buttons[index].grid_configure(row=index // columns, column=index % columns)

    def shortcut(self, command):
        command()
        return "break"

    def other_pane(self, pane):
        return self.target if pane.source else self.source

    def set_active(self, pane):
        self.active_pane = pane

    def focus_filter(self):
        self.active_pane.filter_entry.focus_set()
        self.active_pane.filter_entry.selection_range(0, "end")

    def focus_task(self):
        self.task_tree.focus_set()
        children = self.task_tree.get_children()
        if children and not self.task_tree.focus():
            self.task_tree.focus(children[0])
            self.task_tree.selection_set(children[0])

    def select_all_tasks(self, event=None):
        self.task_tree.selection_set(self.task_tree.get_children())
        return "break"

    def toggle_missing(self):
        self.source.only_missing.set(not self.source.only_missing.get())
        self.source.render()

    def toggle_overwrite(self):
        if not self.running and not self.comparing:
            self.overwrite.set(not self.overwrite.get())
            self.schedule_save()

    def toggle_verify(self):
        if not self.running and not self.comparing:
            self.verify.set(not self.verify.get())
            self.schedule_save()

    def toggle(self, row, refresh=True):
        if self.running or self.comparing or row["is_dir"]:
            return
        key = path_key(row["path"])
        if key in self.items:
            del self.items[key]
        else:
            destination = row.get("destination") or str(Path(self.target.current) / row["name"])
            if any(path_key(item.destination) == path_key(destination) for item in self.items.values()):
                self.status.set("Ziel bereits in der Aufgabe: " + destination)
                return
            self.items[key] = CopyItem(row["path"], destination, row["size"], row["mtime_ns"])
        if refresh:
            self.changed()

    def changed(self):
        self.source.render()
        self.render_task()
        self.schedule_save()

    def render_task(self):
        focus = self.task_tree.focus()
        selection = set(self.task_tree.selection())
        self.task_tree.delete(*self.task_tree.get_children())
        for index, (key, item) in enumerate(self.items.items()):
            self.task_tree.insert("", "end", iid=key, values=(item.source, item.destination,
                                  human_size(item.size), LABELS[item.status]), tags=(item.status,))
            if key in selection:
                self.task_tree.selection_add(key)
        if focus in self.items:
            self.task_tree.focus(focus)
        successes = sum(item.status == "copied" for item in self.items.values())
        self.task_title.set(f" AUFGABE · {len(self.items)} Dateien · "
                            f"{human_size(sum(item.size for item in self.items.values()))} · "
                            f"{successes} erfolgreich · {self.task_path.name if self.task_path else 'automatisch gesichert'} ")

    def schedule_save(self):
        if self.save_after:
            self.root.after_cancel(self.save_after)
        self.save_after = self.root.after(300, self.persist)

    def persist(self):
        self.save_after = None
        try:
            HOME.mkdir(parents=True, exist_ok=True)
            for path in dict.fromkeys([AUTOSAVE] + ([self.task_path] if self.task_path else [])):
                save_task(path, list(self.items.values()), self.source.current, self.target.current,
                          self.overwrite.get(), self.verify.get())
            return True
        except Exception as error:
            self.status.set("Aufgabe konnte nicht gespeichert werden: " + str(error))
            return False

    def save_as(self):
        path = filedialog.asksaveasfilename(parent=self.root, title="Aufgabe speichern",
                   initialdir=str(HOME), initialfile=self.task_path.name if self.task_path else "Kopieraufgabe.json",
                   defaultextension=".json", filetypes=[("Kopieraufgabe", "*.json")])
        if path:
            self.task_path = Path(path)
            if self.persist():
                self.status.set("Aufgabe gespeichert: " + path)
                self.render_task()
            else:
                messagebox.showerror("Speicherfehler", self.status.get(), parent=self.root)

    def apply_task(self, path):
        items, data = load_task(path)
        self.items = {path_key(item.source): item for item in items}
        self.source.current = data["source_directory"]
        self.target.current = data["destination_directory"]
        self.overwrite.set(data.get("overwrite", False))
        self.verify.set(data.get("verify", True))
        self.render_task()

    def restore(self):
        if AUTOSAVE.exists():
            try:
                self.apply_task(AUTOSAVE)
                self.status.set("Letzte Aufgabe wiederhergestellt. F5 setzt sie fort; Erfolge werden auf Änderungen geprüft.")
            except Exception as error:
                self.status.set("Letzte Aufgabe konnte nicht geladen werden: " + str(error))

    def load_dialog(self):
        if self.running or self.comparing:
            return
        path = filedialog.askopenfilename(parent=self.root, title="Aufgabe laden", initialdir=str(HOME),
                                          filetypes=[("Kopieraufgabe", "*.json"), ("Alle Dateien", "*.*")])
        if not path:
            return
        if self.items and not messagebox.askyesno("Aufgabe laden", "Die aktuelle Liste durch die gespeicherte Aufgabe ersetzen?\n"
                                                  "Der aktuelle Stand ist automatisch gesichert.", parent=self.root):
            return
        try:
            self.apply_task(path)
            self.task_path = Path(path)
            self.refresh()
            self.changed()
            self.status.set("Aufgabe geladen: " + path)
        except Exception as error:
            messagebox.showerror("Ladefehler", str(error), parent=self.root)

    def remove_selected(self, event=None):
        if not self.running and not self.comparing:
            for key in self.task_tree.selection():
                self.items.pop(key, None)
            self.changed()
            self.status.set("Einträge aus der Aufgabe entfernt. Dateien auf den Datenträgern bleiben erhalten.")
        return "break"

    def details(self, event=None):
        item = self.items.get(self.task_tree.focus())
        if item:
            messagebox.showinfo("Dateidetails", f"Quelle: {item.source}\n\nZiel: {item.destination}\n\n"
                                f"Status: {LABELS[item.status]}\nKopiert am: {item.copied_at or '–'}\n"
                                f"SHA-256: {item.sha256 or 'nicht geprüft'}\n\n{item.error}", parent=self.root)
        return "break"

    def refresh(self):
        if not self.running and not self.comparing:
            self.source.navigate(self.source.current)
            self.target.navigate(self.target.current)

    def busy_controls(self):
        state = "disabled" if self.running or self.comparing else "normal"
        for label in ("⇧F2 Laden", "F3 Prüfen", "F5 Kopieren", "F8 Entfernen", "F9 Aktualisieren"):
            self.action_buttons[label].configure(state=state)
        for widget in (self.overwrite_check, self.verify_check, self.missing_button,
                       self.source.entry, self.target.entry, self.source.browse_button, self.target.browse_button):
            widget.configure(state=state)

    def compare(self):
        if self.running or self.comparing:
            return
        self.comparing = True
        self.compare_cancel.clear()
        self.source.generation += 1
        self.target.generation += 1
        source, destination = self.source.current, self.target.current
        self.busy_controls()
        self.status.set("Prüfe Quelle und Ziel einschließlich Unterordnern … Esc bricht ab.")

        def worker():
            try:
                rows = compare_directories(source, destination, self.compare_cancel,
                      lambda count: self.events.put(("compare_progress", count)))
                self.events.put(("comparison", rows, ""))
            except CopyCancelled:
                self.events.put(("comparison", None, "Prüfung abgebrochen."))
            except Exception as error:
                self.events.put(("comparison", None, str(error)))
        threading.Thread(target=worker, daemon=True).start()

    def mark_missing(self):
        if self.running or self.comparing:
            return
        if not self.source.comparison_mode:
            self.status.set("Zuerst F3 drücken: Quelle und Ziel rekursiv prüfen.")
            return
        count = 0
        for row in self.source.rows:
            if row.get("comparison") == "missing" and path_key(row["path"]) not in self.items:
                self.toggle(row, refresh=False)
                count += 1
        self.changed()
        self.status.set(f"{count} im Ziel fehlende Dateien zur Aufgabe hinzugefügt (einschließlich Unterordnern).")

    def start_copy(self):
        if self.running or self.comparing:
            return
        if not self.items:
            self.status.set("Zuerst Quelldateien mit Leertaste/Einfg oder Checkboxen auswählen.")
            return
        overwrite, verify = self.overwrite.get(), self.verify.get()
        if overwrite and not messagebox.askyesno("Vorhandene Dateien überschreiben",
                "Die Option zum Überschreiben ist aktiv.\nVorhandene Zieldateien können ersetzt werden.\n\n"
                "Kopieraufgabe jetzt starten?", parent=self.root, default="no"):
            return
        snapshots = [replace(item) for item in self.items.values()]
        self.total_bytes = sum(item.size for item in snapshots)
        self.completed_bytes = 0
        self.started_at = time.monotonic()
        self.file_progress["value"] = self.total_progress["value"] = 0
        self.running = True
        self.cancel.clear()
        self.source.generation += 1
        self.target.generation += 1
        self.busy_controls()
        self.persist()
        self.status.set("Kopieraufgabe läuft · Esc bricht nach dem aktuellen Datenblock ab.")

        def worker():
            counts = Counter()
            for index, item in enumerate(snapshots):
                if self.cancel.is_set():
                    break
                key = path_key(item.source)
                self.events.put(("start", key, index + 1, len(snapshots)))
                result = copy_item(item, self.cancel, overwrite, verify,
                      lambda phase, done, total, key=key: self.events.put(("progress", key, phase, done, total)))
                counts[result] += 1
                self.events.put(("result", key, asdict(item)))
            self.events.put(("finished", dict(counts), self.cancel.is_set()))
        threading.Thread(target=worker, daemon=True).start()

    def abort(self):
        if self.running:
            self.cancel.set()
            self.status.set("Abbruch angefordert. Warte auf laufenden Netzwerk-/Dateizugriff …")
        elif self.comparing:
            self.compare_cancel.set()
            self.status.set("Abbruch der Prüfung angefordert …")
        else:
            self.active_pane.focus_files()

    def handle(self, event):
        kind, *args = event
        if kind == "scan":
            source, generation, directory, rows, error = args
            (self.source if source else self.target).accept_scan(generation, directory, rows, error)
        elif kind == "compare_progress":
            self.status.set(f"Vergleiche … {args[0]} Quelldateien geprüft · Esc bricht ab.")
        elif kind == "comparison":
            rows, error = args
            self.comparing = False
            self.busy_controls()
            if rows is None:
                self.status.set("Prüfung: " + error)
            else:
                self.source.rows, self.source.comparison_mode = rows, True
                self.source.render()
                counts = Counter(row["comparison"] for row in rows)
                self.status.set(f"Prüfung fertig: {counts['missing']} fehlen · {counts['different']} andere Größe/Typ · "
                                f"{counts['equal']} vorhanden (gleicher Name + Größe; keine Inhaltsprüfung). "
                                "Shift+F3 markiert alle fehlenden Dateien.")
                self.source.focus_files()
        elif kind == "start":
            self.active_key, self.active_number, self.active_count = args
        elif kind == "progress":
            key, phase, done, total = args
            item = self.items[key]
            if item.status != phase:
                self.phase_started_at = time.monotonic()
                item.status = phase
                self.render_task()
                self.source.render()
            fraction = done / total if total else 1
            self.file_progress["value"] = fraction * 100
            self.total_progress["value"] = min(100, (self.completed_bytes + (done if phase == "copying" else total))
                                                / max(1, self.total_bytes) * 100)
            elapsed = max(0.01, time.monotonic() - self.phase_started_at)
            speed = done / elapsed
            self.progress_text.set(f"{self.active_number}/{self.active_count} · {LABELS[phase]} "
                                   f"{Path(item.source).name} · {human_size(done)} / {human_size(total)} "
                                   f"({fraction:.0%}) · Ø {human_size(speed)}/s")
        elif kind == "result":
            key, data = args
            self.items[key] = CopyItem(**data)
            if data["status"] == "copied" and self.source.comparison_mode:
                for row in self.source.rows:
                    if path_key(row["path"]) == key:
                        row["comparison"] = "equal"
            self.completed_bytes += data["size"]
            self.changed()
        elif kind == "finished":
            counts, aborted = args
            self.running = False
            self.busy_controls()
            if not aborted:
                self.total_progress["value"] = 100
            self.status.set(("Abgebrochen" if aborted else "Aufgabe beendet")
                + f" · {counts.get('copied', 0)} erfolgreich · {counts.get('exists', 0)} vorhanden/übersprungen"
                + f" · {counts.get('error', 0)} Fehler · Details: F6, Datei wählen, Enter")
            self.progress_text.set(self.status.get())
            self.persist()
            # Keep comparison results visible, refresh just the local target listing.
            if not self.closing and not self.source.comparison_mode:
                self.target.navigate(self.target.current)
            if not counts.get("error") and not aborted:
                self.root.bell()

    def poll(self):
        try:
            for _ in range(150):
                self.handle(self.events.get_nowait())
        except queue.Empty:
            pass
        if self.closing and not self.running and not self.comparing:
            self.finish_close()
            return
        self.root.after(80, self.poll)

    def close(self):
        if self.running or self.comparing:
            self.closing = True
            self.abort()
        else:
            self.finish_close()

    def finish_close(self):
        if not self.persist():
            self.closing = False
            if not messagebox.askyesno("Speichern fehlgeschlagen", self.status.get()
                    + "\n\nTrotzdem beenden?", parent=self.root, default="no"):
                self.root.after(80, self.poll)
                return
        self.root.destroy()

    def help(self):
        messagebox.showinfo("Kopier Commander · Tastatur", ""
            "Tab / Shift+Tab     Zwischen Quelle und Ziel wechseln\n"
            "Pfeiltasten / Pos1 / Ende / Bild↑↓     In der Dateiliste navigieren\n"
            "Leertaste / Einfg     Datei an-/abwählen, eine Zeile weiter\n"
            "Enter     Ordner öffnen / Quelldatei an-/abwählen\n"
            "Rücktaste     Übergeordnetes Verzeichnis\n"
            "Strg+A     Alle sichtbaren Quelldateien vormerken\n"
            "Strg+Shift+A     Sichtbare Quelldateien abwählen\n"
            "Strg+I     Auswahl der sichtbaren Dateien umkehren\n"
            "Alt+M     Nur im Ziel fehlende Dateien anzeigen\n"
            "Alt+U / Alt+H     Überschreiben / SHA-256 umschalten\n"
            "Alt+S / Alt+Z     Quell-/Zielpfad bearbeiten (Enter übernimmt)\n"
            "Strg+L     Pfad des aktiven Dateifensters bearbeiten\n\n"
            "F2 / Strg+S     Aufgabe als JSON speichern\n"
            "Shift+F2 / Strg+O     Aufgabe laden\n"
            "F3     Rekursiver Vergleich: relativer Pfad und Größe\n"
            "Shift+F3     Alle im Vergleich fehlenden Dateien vormerken\n"
            "F4     Namensfilter des aktiven Fensters bearbeiten\n"
            "F5     Kopierliste starten / fortsetzen\n"
            "F6     Aufgabenliste fokussieren, Enter zeigt Details\n"
            "F8 / Entf in Aufgabe     Markierte Aufgaben entfernen\n"
            "F9     Beide Dateifenster aktualisieren\n"
            "Esc     Kopieren/Prüfen abbrechen\n"
            "F10     Speichern und beenden\n\n"
            "Zielpfade werden beim Ankreuzen festgelegt. Ein späterer Wechsel\n"
            "des Zielordners betrifft nur neu ausgewählte Dateien.\n"
            "Im rekursiven Vergleich bleibt die Unterordnerstruktur erhalten.\n"
            "Grün = erfolgreich kopiert; Gelb = ausgewählt/fehlend; Rot = Fehler/abweichend.\n"
            "Vorhanden bedeutet gleicher Name und Größe, keine Inhaltsgarantie.\n"
            "SHA-256 prüft neue Kopien; gespeicherte Erfolge werden vor dem\n"
            "Fortsetzen anhand Größe und Änderungszeit auf Änderungen geprüft.\n"
            "Die letzte Aufgabe und ihr Fortschritt werden automatisch gespeichert.", parent=self.root)
