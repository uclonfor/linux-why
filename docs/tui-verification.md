# TUI engineering verification

Verified on 2026-09-09 in the existing Ubuntu/PRoot aarch64 environment.

## Architecture and reused code

- Textual is a presentation/input layer; `core.resolver.resolve(Context)` is shared
  with direct CLI mode. Existing inspectors, provenance claims, JSON schema and
  text renderer remain in use.
- Package inventory extends the existing pacman/dpkg backends. Other inventories
  reuse procfs, FS, Context socket parsing, Runner, and systemd JSON commands.
- Inventories are lazy session snapshots. Filtering is local; an explanation is a
  fresh query. F2 redraws the same graph with evidence sources.
- Runtime dependencies: Textual 6.12–6.x and pyfiglet 1.x. pytest-asyncio is a
  development dependency. Direct CLI imports neither TUI dependency at startup.

## Keyboard/event review

- Initial focused selection is Installed packages; Enter opens its browser.
  The Exit menu item was removed on 2026-09-10; Ctrl+Q remains the quit shortcut.
- OptionList owns arrow, page and Home/End navigation. There is no Input widget
  competing for keys. Printable Unicode, q, punctuation and paste extend search.
- Backspace edits only a nonempty query; empty Backspace preserves selection.
- Esc clears search first, then goes back. Result return restores list focus.
- Option epochs reject events from replaced lists; result generations reject
  late worker completions. Empty lists and shrinking filters are tested.
- Ctrl+Q cancels workers and prevents new external commands. An in-flight command
  retains the existing bounded timeout; no subprocess is started per keypress.
- A failed systemd status inventory displays unknown, not an assumed unloaded
  state. Port inventory grouping is linear in the number of socket records.

## FIGlet

Actually rendered and compared slant, small, standard, big, doom and ansi_shadow.
Selected standard: 47 columns × 6 rows for linux-why. The application measures the
rendered width and switches to plain linux-why when it will not fit, or on a short
screen. `docs/tui.svg` is a real export from Textual's running 80×24 renderer.

## Manual PTY verification (2026-09-09, before the menu revision)

The installed console command was exercised in a real PTY:

- Initial Exit → Enter → exit code 0.
- Down → Enter → Installed packages, followed by immediate fire filtering.
- Esc clears the browser query; a second Esc returns home.
- Global fire search → Enter → explanation → Esc restores the search.
- qemu enters a query and does not quit on q.
- Ctrl+Q exits cleanly. The original termios settings, visible cursor and normal
  screen were verified after exit.

Additional PTYs: 80×24/vt100, 140×45/xterm and 35×16/xterm-256color, without
truecolor and with simulated SSH environment variables. TERM=dumb exits with
clear guidance and never enters the alternate screen. Non-TTY stdout/stdin also
return the documented guidance and exit 2.

A real SSH transport was not available; simulated SSH variables plus an allocated
PTY are not claimed as an end-to-end SSH test. Live Arch/pacman and unrestricted
proc socket integration remain unavailable in this environment.

## Automated checks

The full suites run on Python 3.12.14 and 3.13.15. See the final engineering report
for the exact final counts. The existing CLI/provenance suite is retained, including
namespace, module-file provenance, permissions and JSON regression checks. New
Textual Pilot tests cover input/focus/navigation, Unicode/paste, empty/stale lists,
logo fallback, all supported terminal sizes and clean exit. Inventory tests verify
bulk query counts, cache reuse and unknown states on failed discovery.

No application was published. Browser snapshots are refreshed by restarting the
TUI; live refresh and a real SSH/Arch validation run remain future validation work.
