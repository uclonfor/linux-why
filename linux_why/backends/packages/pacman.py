"""Local libalpm queries via pacman. LC_ALL=C is imposed by Runner.

pacman exposes no structured query-info format. Parse anchored labels and wrapped
continuations; never split on arbitrary colons inside field values. expac is an
optional structured cross-check, not a requirement.
"""

import re

from linux_why.backends.packages.base import Package, PackageBackend
from linux_why.utils.command import Runner
from linux_why.utils.fs import FS


def fields(text: str) -> dict[str, str]:
    output: dict[str, str] = {}
    current = ""
    for line in text.splitlines():
        match = re.match(r"^([A-Za-z][A-Za-z ]*?)\s+: (.*)$", line)
        if match:
            current = match[1].strip()
            output[current] = match[2].strip()
        elif line[:1].isspace() and current:
            output[current] += " " + line.strip()
    return output


class Pacman(PackageBackend):
    name = "pacman"

    def __init__(self, runner: Runner, fs: FS) -> None:
        self.runner, self.fs = runner, fs
        self.cache: dict[str, Package] = {}
        self.log: str | None = None

    def get(self, name: str) -> Package | None:
        if name in self.cache:
            self.problem = None
            return self.cache[name]
        result = self.runner.run(["pacman", "-Qi", "--", name])
        self.problem = result.problem
        if result.code:
            if result.stderr and "was not found" not in result.stderr:
                self.problem = result.stderr.strip()
            return None
        data = fields(result.stdout)
        if data.get("Name") != name or not data.get("Version"):
            self.problem = "Malformed pacman query output"
            return None
        reason = {
            "Explicitly installed": "explicit",
            "Installed as a dependency for another package": "dependency",
        }.get(data.get("Install Reason", ""), "unknown")
        required = data.get("Required By", "None")
        pkg = Package(
            name,
            data["Version"],
            self.name,
            reason,
            [] if required == "None" else required.split(),
            data.get("Install Date"),
            "pacman -Qi",
        )
        if "Required By" not in data or reason == "unknown":
            pkg.warnings.append("pacman did not provide complete dependency metadata")
        if self.runner.which("expac"):
            extra = self.runner.run(["expac", "%n\t%v", "--", name])
            if extra.code == 0 and extra.stdout.strip() != f"{name}\t{pkg.version}":
                pkg.warnings.append("Package database changed during query (expac cross-check)")
        if self.log is None:
            try:
                self.log = self.fs.tail("/var/log/pacman.log")
            except OSError:
                self.log = ""
        events = re.findall(
            r"^\[([^\]]+)\] \[ALPM\] installed " + re.escape(name) + r" \(([^\n]+)\)$",
            self.log,
            re.MULTILINE,
        )
        if events:
            pkg.log_event = f"{events[-1][0]} installed {name} ({events[-1][1]})"
        self.cache[name] = pkg
        return pkg

    def owner(self, path: str) -> list[str]:
        result = self.runner.run(["pacman", "-Qqo", "--", path])
        self.problem = result.problem
        if result.code and result.stderr and "No package owns" not in result.stderr:
            self.problem = result.stderr.strip()
        return result.stdout.splitlines() if result.code == 0 else []

    def list_installed(self) -> list[Package]:
        result = self.runner.run(["pacman", "-Q"])
        self.problem = result.problem
        if result.code:
            self.problem = result.problem or result.stderr.strip() or "pacman inventory failed"
            return []
        explicit = self.runner.run(["pacman", "-Qqe"])
        reasons_known = explicit.code == 0
        if not reasons_known:
            self.problem = explicit.problem or "pacman explicit package inventory unavailable"
        names = set(explicit.stdout.splitlines()) if reasons_known else set()
        packages = []
        for line in result.stdout.splitlines():
            fields = line.split()
            if len(fields) != 2:
                self.problem = "Malformed pacman inventory record skipped"
                continue
            name, version = fields
            reason = ("explicit" if name in names else "dependency") if reasons_known else "unknown"
            packages.append(
                Package(name, version, self.name, reason, evidence="pacman -Q; pacman -Qqe")
            )
        return packages
