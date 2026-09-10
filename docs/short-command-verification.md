# Short command verification

Verified 2026-09-10, Python 3.12, Ubuntu/PRoot on Android/Termux.

`why` and `linux-why` are console_scripts for `linux_why.cli:main`. No CLI,
resolver, inspector, graph, TUI or chooser implementation changed.

Built the wheel and installed it using ordinary pip into a fresh venv, without
system site packages, outside the source directory and without PYTHONPATH.
Verified the module imported from that venv's site-packages, `command -v` found
both installed executables, and both `--help` and `--version` succeeded.
Ran `why firefox`, `why package:firefox`, `why /usr/bin/bash` and `why lo`.
Unavailable host data remains an ordinary partial result, including command
timeouts; live observations need not be byte-identical across sequential runs.

Real PTY checks of the installed wheel:

- `why` opened the existing TUI; Ctrl+Q exited with code 0.
- `why bash --depth 0 --no-color` opened the ambiguity chooser; Down/Enter and
  numeric 2 selected the executable and printed the ordinary explanation.
- Esc and Ctrl+C cancelled; narrow terminals, resize and vt100 worked.
- termios matched its initial state; cursor-show and alternate-screen teardown
  sequences were present after exit.
- `why firefox` was executed in a real PTY. Firefox is absent on this host, so
  that query was unresolved. To verify the exact ambiguity spelling separately,
  a temporary PATH fixture supplied a dummy firefox file and deterministic
  dpkg-query package data. The installed `why firefox` opened the chooser and
  Down/Enter explained that fixture's executable. No system files were changed.

The packaging regression test performs a fresh wheel installation when
LINUX_WHY_TEST_WHEEL names a wheel. CI runs it after the package build on both
Python versions. Ordinary offline pytest runs skip that installation step.
All tests of normalized targets continue to use the existing resolver pipeline.
