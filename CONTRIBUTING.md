# Contributing

Bug reports, documentation improvements and focused pull requests are welcome.

## Local setup

Use Python 3.10 or newer with Tkinter. Run directly from the checkout:

```console
python run.py
python run_tests.py
```

No third-party runtime packages are required. Package installation for development
is optional: `python -m pip install -e .`.

## Code layout

- `src/kopier_commander/core.py`: copy engine, comparison, task serialization.
- `src/kopier_commander/app.py`: Tkinter UI and worker-event processing.
- `src/kopier_commander/cli.py`: command-line startup.
- `src/kopier_commander/config.py`: per-user state location.
- `tests/`: engine tests and a real Tk keyboard integration test.

Keep filesystem and network work off the Tk main thread. Workers communicate
through the event queue; they must not call Tk widgets. Preserve the distinction
between files copied by a task and files that merely existed already. Do not
enable overwriting by default.

Run the test suite for behavior changes. Add focused tests for data integrity,
task persistence, cancellation or keyboard behavior when changing those areas.
GUI tests need a desktop or Xvfb.

## Reports and test data

Include the Python version, operating system, reproduction steps and relevant
error text. Replace private filenames, NAS addresses and local paths with
invented examples. Do not attach credentials, real task JSON files or media files.

By contributing, you agree that your contribution is licensed under the MIT
license in this repository.
