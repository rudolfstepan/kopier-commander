# Kopier Commander

A keyboard-friendly, two-pane file copy manager for local folders and Windows
network shares. Inspired by classic Commander interfaces, with blue file panels,
cyan borders, yellow selections and a function-key bar.

**Python 3.10+ · Tkinter · No third-party runtime dependencies · MIT license**

The current interface is German. Windows is the primary tested desktop platform;
the copy engine also supports POSIX filesystems. Linux desktop support is included
in the CI workflow, but has not yet been verified on a physical Linux desktop.

## Features

- Select individual source files with checkboxes, Space or Insert.
- Browse two independent directories, sort columns and filter filenames.
- Compare source and target recursively by relative filename and file size.
- Filter missing files and add all missing files to a copy task.
- Keep relative subdirectories when selecting from the recursive comparison.
- Save and load tasks as JSON, including per-file results and SHA-256 checksums.
- Automatically save progress and restore the last task at startup.
- Mark successful copies in green; distinguish existing targets from actual copies.
- Copy in a background thread, with per-file progress and cancellation.
- Verify newly copied data with SHA-256 by default.
- Publish completed copies from temporary files; skip existing targets by default.
- Use a matching two-pane copy icon for the application and Windows launch shortcut.

## Run from source

```console
python run.py
```

On Windows, double-click `Start-KopierCommander.cmd`. Python with Tcl/Tk support
must be installed and available on `PATH`. The standard Windows Python installer
includes an option to install Tcl/Tk. There are no packages to install for running
from source.

Choose the source with **Alt+S** and the target with **Alt+Z**. Press Enter after
entering each path. Both panels initially point to your home directory.

You can also start with explicit paths:

```console
python run.py --source "\\nas\media\Movies" --target "D:\Movies"
python run.py --task "D:\Tasks\weekend-copy.json"
python run.py --help
```

Supplying `--source` or `--target` starts a new, empty task instead of restoring
the last task. `--task` loads a saved task and cannot be combined with these path
options. Paths can always be changed through the GUI.

### Windows shortcut and app icon

![Kopier Commander icon](src/kopier_commander/assets/kopier-commander-48.png)

The blue icon shows two file panels and a yellow copy arrow. It appears in the
application's title bar and Windows taskbar. To create a launch shortcut with
the same icon, open PowerShell in the project folder and run:

```powershell
.\tools\Create-Shortcut.ps1
```

Double-click the resulting `Start-KopierCommander.lnk` to start the application.
Explorer may hide the `.lnk` extension. The shortcut starts the existing CMD
launcher, sets the project folder as the working directory and uses the supplied
ICO file. Python with Tcl/Tk must still be installed.

You can copy the shortcut to your desktop. Keep the project folder and its icon
assets together. After moving or renaming the project folder, rerun the script
and replace any desktop copy of the shortcut. Generated shortcuts are excluded
from Git because they contain absolute local paths. A fresh clone needs its own
shortcut; the supplied icons are ready to use.

### Install as a Python package

```console
python -m pip install .
kopier-commander
```

Alternatively, run `python -m kopier_commander` after installation. Building or
installing the package requires setuptools; pip may download it. Tkinter is part
of the Python installation, not a pip dependency. On Linux, install your system's
Tkinter package if necessary.

## Typical workflow

1. Set source and target directories with Alt+S and Alt+Z.
2. Press **F3** to compare all source files, including subdirectories.
3. Press **Alt+M** to show only missing files, or inspect the full result.
4. Press **Shift+F3** to add all missing files to the task. Alternatively, use
   Space/Insert to select individual files.
5. Press **F2** to save a named task and **F5** to copy.
6. Completed copies turn green. Press **F6**, choose a task item and press Enter
   to view its result, checksum or error.

A comparison checks relative filenames and sizes; it does **not** prove that
already existing files have identical contents. SHA-256 verification applies to
new copies. Refresh the comparison with F3 when files change externally.

## Keyboard controls

| Key | Action |
| --- | --- |
| Tab / Shift+Tab in a file list | Switch source and target panels |
| Arrows, Home, End, Page Up/Down | Navigate a list |
| Space / Insert in source | Toggle file selection and move down |
| Enter | Open a directory or toggle a source file |
| Backspace | Open parent directory |
| Ctrl+A in source | Add all visible source files |
| Ctrl+Shift+A in source | Remove visible files from the task |
| Ctrl+I in source | Invert visible file selection |
| Alt+S / Alt+Z | Edit source / target path |
| Ctrl+L in a file list | Edit that panel's path |
| Alt+M | Toggle missing-files filter |
| Alt+U / Alt+H | Toggle overwrite / SHA-256 verification |
| F1 | Help |
| F2 / Ctrl+S | Save task as JSON |
| Shift+F2 / Ctrl+O | Load task |
| F3 | Recursive source/target comparison |
| Shift+F3 | Add all missing files from the comparison |
| F4 | Focus active panel's name filter |
| F5 | Start or continue copying |
| F6 | Focus the task list |
| Ctrl+A in task list | Select all task entries |
| F8 / Delete in task list | Remove selected task entries |
| F9 | Refresh both panels |
| Escape | Cancel copying/comparison |
| F10 | Save and exit |

F8 only removes task entries. It does not delete source or target files. Shift+F3
uses the entire comparison, even when a name filter hides some results.

## Copy behavior and limits

The target path is captured when a source checkbox is selected. Changing the
right panel later affects newly selected files. Inspect the task list to see the
full source and target paths.

Existing targets are skipped unless overwrite is enabled. Starting an overwrite
task requires confirmation. Existing files are not marked as successful copies
just because their filename or size matches.

Files are written to unique `.kopier-*.part` files in the destination directory.
The source is hashed while reading, and the temporary target is read back for
SHA-256 verification. The final filename is published only after completion.
This adds a local read pass; it does not read the NAS source a second time.

Normal errors and cancellation remove partial temporary files. A power loss or
forced process termination can leave `.part` files behind. A cancelled file
starts again from its beginning; there is no partial-file resume. Cancellation
waits for any blocked operating-system/network operation to return.

Saved successes are checked against source and target sizes and modification
times before being skipped on continuation. This is a metadata check, not a new
checksum scan of old files. File contents modified without changing their size
and timestamp will not be detected by that continuation check.

The application preserves file modification times. It is a file-copy tool, not a
full backup/synchronization system: it does not mirror deletions, copy empty
directories, reproduce ACLs or promise preservation of alternate data streams.
Run one instance per task; simultaneous edits to the same task file are not merged.

## Saved state and privacy

Automatic state is stored outside the source checkout:

| Platform | Default location |
| --- | --- |
| Windows | `%LOCALAPPDATA%\KopierCommander\letzte-aufgabe.json` |
| Linux | `$XDG_DATA_HOME/kopier-commander/letzte-aufgabe.json`, defaulting to `~/.local/share/...` |
| macOS | `~/Library/Application Support/KopierCommander/letzte-aufgabe.json` |

Override the state directory with `--data-dir` or `KOPIER_COMMANDER_DATA_DIR`.
Named tasks selected with F2 are also updated throughout that session.

Task files contain absolute file paths and may reveal network hostnames or media
filenames. They are excluded from Git. The project contains no personal task
files, NAS addresses, credentials or media files. Existing task files from the
original standalone version can be opened with Shift+F2 without conversion.

For Windows shares, access is handled by your Windows user session. Open the
share in Explorer and sign in there if access is denied. The application does not
collect or store NAS passwords.

## Development

```console
python run_tests.py
```

Tests use temporary files and directories. They do not access a real NAS or movie
library. The GUI test creates a Tk window, sends keyboard events and verifies
comparison, selection, copying, saved results and layout at the minimum size.
It requires an interactive desktop. On headless Linux:

```console
xvfb-run -a python run_tests.py
```

The GitHub Actions workflow defines Windows tests for Python 3.10 and 3.14, a
Windows wheel build, and Linux tests under Xvfb. Hosted CI runs start only after
the repository is published.

See [CONTRIBUTING.md](CONTRIBUTING.md), [the changelog](CHANGELOG.md) and the
[German quick guide](docs/bedienung.md).

The icon assets are included in Python packages as well as source checkouts.
To redraw all icon sizes with Windows PowerShell and .NET drawing tools
(no extra packages required), run from the project folder:

```powershell
.\tools\Build-Icons.ps1
```

See [the contributor guide](CONTRIBUTING.md#icon-assets) for asset formats and
packaging details.

## License

[MIT](LICENSE), copyright 2026 Rudolf Stepan. This is an independent project;
the Commander reference describes its interface inspiration and implies no
affiliation with the original Norton Commander product.
