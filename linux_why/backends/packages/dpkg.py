"""Basic Debian ownership/version support; deliberately no guessed reverse graph."""

from linux_why.backends.packages.base import Package, PackageBackend
from linux_why.utils.command import Runner


class Dpkg(PackageBackend):
    name = "dpkg"

    def __init__(self, runner: Runner) -> None:
        self.runner = runner

    def get(self, name: str) -> Package | None:
        result = self.runner.run(
            [
                "dpkg-query",
                "-W",
                "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n",
                "--",
                name,
            ]
        )
        self.problem = result.problem
        if result.code:
            if result.stderr and "no packages found" not in result.stderr:
                self.problem = result.stderr.strip()
            return None
        parts = result.stdout.strip().split("\t")
        if len(parts) != 3 or parts[2] != "installed":
            return None
        pkg = Package(parts[0], parts[1], self.name, evidence="dpkg-query -W")
        pkg.warnings.append(
            "Debian backend is basic: install reason and reverse dependencies unavailable"
        )
        return pkg

    def owner(self, path: str) -> list[str]:
        result = self.runner.run(["dpkg-query", "-S", "--", path])
        self.problem = result.problem
        if result.code and result.stderr and "no path found" not in result.stderr:
            self.problem = result.stderr.strip()
        owners: list[str] = []
        if result.code == 0:
            for line in result.stdout.splitlines():
                owner, separator, file = line.partition(": ")
                if separator and file == path and not owner.startswith("diversion "):
                    owners.extend(owner.split(", "))
        return owners

    def list_installed(self) -> list[Package]:
        result = self.runner.run(
            [
                "dpkg-query",
                "-W",
                "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n",
            ]
        )
        self.problem = result.problem
        if result.code:
            self.problem = result.problem or result.stderr.strip() or "dpkg inventory failed"
            return []
        packages = []
        for line in result.stdout.splitlines():
            fields = line.split("\t")
            if len(fields) != 3:
                self.problem = "Malformed dpkg inventory record skipped"
                continue
            name, version, status = fields
            if status == "installed":
                packages.append(Package(name, version, self.name, evidence="dpkg-query -W"))
        return packages
