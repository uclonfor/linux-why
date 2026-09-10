# Ambiguity chooser verification

Verified 2026-09-10 in Ubuntu/PRoot on the Android/Termux host.

- Real console command `linux-why bash --depth 0 --no-color` stayed alive at
  ambiguity, then Down/Enter and numeric 2 selected `/usr/bin/bash`. Ordinary
  explanation output followed alternate-screen teardown. The explanation returned
  3 because this host has restricted system observations.
- Esc and Ctrl+C cancelled with code 0 and no traceback.
- Tested 80x24 xterm, 80x24 vt100 (no truecolor), 30x14 narrow, and 100x32;
  resized each live chooser via TIOCSWINSZ and SIGWINCH before selection.
- Checked complete termios equality before/after, cursor-show and alternate-screen
  exit sequences. SSH environment variables were simulated; no actual remote SSH
  session was available.
- Automated PTY tests cover cancellation and selection followed by plain stdout.
  Headless Textual tests cover immediate focus, arrows, numbers, invalid numbers,
  long lists, resize and scroll. CLI fixture tests use the real detector/resolver
  for raw firefox -> file:/usr/bin/firefox, cancellation, JSON, each non-TTY
  stream, TERM=dumb, and explicit package targets.
- Existing package-browser test additionally asserts `package:firefox` reaches
  the resolver. All inventories retain their existing typed targets.

Key-event review: OptionList exclusively handles navigation/Enter. App bindings
handle cancellation, and digit events are consumed once. Selection is returned
from the normalized Candidate, never parsed from its display label. The CLI
invokes the chooser at most once, then starts a fresh explicit Context. No
subprocesses run inside the chooser. JSON and non-TTY gates run before importing
or launching it. No new dependencies were introduced.

Live Arch/pacman and proc socket integration remain unavailable on this host;
those existing tests skip explicitly rather than reporting successful coverage.
