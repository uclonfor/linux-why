# Architecture and evidence contract

`cli` → `detector` → `Context.expand` → per-object inspector → `Graph` → renderer/JSON.
Inspectors share only the context, graph models, and small backend interfaces.
`Runner` is the sole subprocess boundary. `FS` can be rooted in a fixture directory.
No plugin discovery or arbitrary Python loading occurs at runtime.

A `Claim` associates a value, source and confidence. Edges point from the queried
object towards explanatory context; relation names make direction explicit:
`REQUIRED_BY`, `OWNED_BY`, `CHILD_OF`, `MEMBER_OF`, `HELD_BY`.
`HELD_BY` describes a procfs FD observation, not historical socket creation.
`REQUIRED_BY` records current package metadata and is never relabeled
`INSTALLED_BECAUSE_OF`. No historical installation cause is inferred in 0.1.

Cycles are valid data. Query expansion caches visited objects with their shallowest
visited depth; render traversal prints repeated nodes once and marks repeat links.
Depth counts resolver transitions. A socket match grouping adds a display edge but
not an inspector transition. Work limits produce warnings, and system limitations
set `partial`; expected absent targets return no root.

To add a package backend, implement `get` and `owner`, preserve unknown install
reasons, and register the distribution family in `utils/platform.py`. To add an
inspector, register one `(Context, value, depth) -> Node | None` function. Use context
expansion for cross-subsystem links and give every relation an evidence source.

The common Linux interfaces are not transactionally consistent. A successful read
is confirmed only for that read. PID start-time guards reduce reuse races; process
exit, permission failures, missing commands, and parsing failures are reported.


## Interactive presentation

`cli.main` routes an absent target to `tui.app.WhyApp` after checking stdin/stdout
TTY status and TERM. A target still uses the direct pipeline. Both paths call
`core.resolver.resolve(Context)`; the JSON model and inspectors are unchanged.

`core.inventory.Catalog` is opt-in discovery, independent of Textual. Package
inventory belongs to the existing package backends (`list_installed`). Unit
inventory joins systemctl JSON records. Other lists reuse Context/procfs/FS.
Inventories select objects; they never serve as evidence for result graphs.

Textual's OptionList owns list navigation and stays focused. The app handles only
printable keys, Backspace and paste for searching. There is no competing Input
widget. Arrow/Home/End/Page keys retain the widget's native bindings. Result
views focus RichLog, then restore the prior list and selection on Esc.

Background workers post messages to the UI thread. A generation counter rejects
late explanations after navigation; option epochs reject selection events from
replaced lists. A stop event prevents new external commands during shutdown;
an in-flight command keeps the existing three-second timeout. Catalog acquisition
is locked and cached, so new keypresses never start duplicate inventory commands.

The pyfiglet standard font was chosen after rendering slant, small, standard, big,
doom and ansi_shadow in a terminal. The generated banner is cached and its actual
width is measured before display; narrow/short screens use the compact name.

Direct CLI ambiguity uses a separate compact `InterpretationChooser` Textual app.
It consumes detector Candidates, returns `Candidate.explicit_target`, and exits
before the ordinary CLI renderer prints the explanation. The CLI creates a fresh
Context for that target, preserving depth and renderer options. No discovery or
provenance code lives in the chooser. The explicit-target property is also used
for main TUI ambiguity entries and does not change Candidate JSON serialization.
Both streams must be TTYs, TERM must be usable, and JSON must be disabled before
the chooser can run. Non-interactive ambiguity remains schema 1.0 with exit 2.
