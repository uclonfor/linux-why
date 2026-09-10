# Verification report

Executed on 2026-09-09 in Ubuntu 26.04 (aarch64, PRoot environment).

## Quality gates

- Python 3.12.14: 86 passed, 2 skipped.
- Python 3.13.15: 86 passed, 2 skipped.
- Ruff check and format check passed.
- Strict mypy passed for 27 source files.
- Wheel and sdist built successfully; wheel includes schema.json.
- Archive inspection confirmed no virtualenv or graphify development state.

Skipped integration tests: live Arch pacman and a real socket listener (proc socket tables inaccessible). The real process and loopback interface integration tests passed.

## Manual CLI probes

`--help` and `--version` passed. These JSON queries completed without tracebacks:

| Target | Exit | Nodes | Interpretation |
| --- | ---: | ---: | --- |
| `/usr/bin/bash` | 3 | 13 | file |
| `systemd` | 3 | 1 | package |
| `systemd.service` | 3 | 0 | unit |
| `live harness PID` | 3 | 10 | process |
| `:22` | 3 | 0 | socket |
| `lo` | 3 | 1 | interface |
| `loop` | 3 | 1 | module |
| `package:linux-why-no-such-package-987654` | 1 | 0 | package |

File, package, process, interface and module queries returned observable data with explicit limitations. systemd.service could not be inspected because this environment is not booted with systemd. :22 was inconclusive because the proc socket tables are inaccessible; no claim is made that port 22 is absent. Exit 3 is the documented partial/inconclusive status.

## Second review

A separate second review pass checked causal semantics, argument handling, parsing, permissions, race conditions, cycles and partial results. Confirmed issues fixed with regression tests:

- Unknown module load state is no longer reported as false.
- A modinfo filename is AVAILABLE_FROM, not proof of where running code was loaded.
- Executable paths in other/unreadable mount namespaces are not assigned host package ownership.
- PID start-time mismatches discard identity-dependent cross-links.
- Cached package success clears unrelated prior backend errors.
- A nonzero systemctl exit with LoadState=not-found remains a normal absent target.
- Detection failures in one filesystem source preserve other interpretations.
- Invalid ip JSON preserves an interface already proven by sysfs.

Graphify TypeScript hook rebuilt the local source graph; portable-check passed. No Git changes were staged or committed, and no artifacts were published.

## Release validation still required

Run the integration suite on a real Arch Linux host with systemd and ordinary procfs/sysfs visibility, with and without expac. Validate socket ownership as an unprivileged user. Debian support is intentionally basic; RPM and evidence-based network-manager attribution remain future work.
