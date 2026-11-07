# Changelog

## Unreleased

- Add a blue two-pane copy icon to application windows and the Windows taskbar.
- Add a script to create a Windows launch shortcut with the same icon.
- Include PNG and multi-size ICO assets in Python distributions, with a
  PowerShell drawing script to regenerate them.
- Document shortcut setup, desktop use and regeneration after moving a checkout.

## 0.1.0 — 2026-11-07

- Extract the standalone copy application into an installable Python package.
- Include the Commander-style, keyboard-friendly two-pane GUI.
- Support recursive comparison, missing-file selection and JSON copy tasks.
- Include SHA-256 verification, cancellation and per-file completion tracking.
- Replace personal directory defaults with home directories and CLI options.
- Store automatic task state in the user's application-data directory.
- Add the MIT license, documentation, tests and CI workflow.
