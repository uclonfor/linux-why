from linux_why.utils.command import Result, Runner

PROPERTIES = (
    "Id",
    "Names",
    "LoadState",
    "ActiveState",
    "SubState",
    "UnitFileState",
    "MainPID",
    "ExecStart",
    "FragmentPath",
    "DropInPaths",
    "Requires",
    "Wants",
    "Requisite",
    "BindsTo",
    "RequiredBy",
    "WantedBy",
    "TriggeredBy",
    "Triggers",
    "PartOf",
    "After",
)


def show(runner: Runner, name: str) -> tuple[dict[str, str], Result]:
    result = runner.run(
        [
            "systemctl",
            "--no-pager",
            "--no-ask-password",
            "show",
            "--property=" + ",".join(PROPERTIES),
            "--",
            name,
        ]
    )
    data = dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)
    return data, result


def list_services(runner: Runner) -> tuple[list[tuple[str, str, str]], list[str]]:
    """Inventory only: join JSON unit-file and loaded-unit snapshots by exact name."""
    import json
    import posixpath

    states: dict[str, tuple[str, str]] = {}
    warnings: list[str] = []
    for verb in ("list-unit-files", "list-units"):
        result = runner.run(
            [
                "systemctl",
                "--no-pager",
                "--no-ask-password",
                "--output=json",
                "--type=service",
                "--all",
                verb,
            ]
        )
        if result.code:
            warnings.append(result.problem or result.stderr.strip() or f"systemctl {verb} failed")
            continue
        seen: set[str] = set()
        try:
            rows = json.loads(result.stdout)
            if not isinstance(rows, list):
                raise ValueError("Expected JSON array")
            for row in rows:
                if not isinstance(row, dict):
                    raise ValueError("Expected unit record")
                if verb == "list-unit-files":
                    name = posixpath.basename(str(row["unit_file"]))
                    states[name] = ("unknown", str(row.get("state", "unknown")))
                else:
                    name = str(row["unit"])
                    seen.add(name)
                    states[name] = (
                        str(row.get("active", "unknown")),
                        states.get(name, ("", "unknown"))[1],
                    )
            if verb == "list-units":
                for name, (_, enabled) in states.items():
                    if name not in seen:
                        states[name] = ("not loaded", enabled)
        except (ValueError, KeyError):
            warnings.append(f"Malformed systemctl {verb} JSON; inventory may be incomplete")
    return [(name, *state) for name, state in sorted(states.items())], warnings
