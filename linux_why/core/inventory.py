"""Opt-in local discovery for browsers. No provenance is inferred here.

Inventories are snapshots for selection; opening an entry always resolves it afresh.
Direct CLI queries never call these potentially broad inventory operations.
"""

import json
import os
from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Lock

from linux_why.backends import procfs, systemd
from linux_why.core.graph import Context

CATEGORIES = {
    "package": "Installed packages",
    "unit": "Systemd services",
    "socket": "Listening ports",
    "process": "Running processes",
    "interface": "Network interfaces",
    "module": "Kernel modules",
}


@dataclass(frozen=True)
class Entry:
    category: str
    name: str
    target: str
    detail: str = ""


@dataclass
class Inventory:
    entries: list[Entry] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


class Catalog:
    """Thread-safe, lazy session cache; each category is acquired at most once."""

    def __init__(self, factory: Callable[[], Context] | None = None) -> None:
        self.factory = factory or (lambda: Context("inventory"))
        self.cache: dict[str, Inventory] = {}
        self.lock = Lock()

    def load(self, category: str) -> Inventory:
        with self.lock:
            if category not in self.cache:
                ctx = self.factory()
                try:
                    entries = collect(ctx, category)
                except (OSError, ValueError) as exc:
                    ctx.warning(f"{category} inventory unavailable: {exc}")
                    entries = []
                self.cache[category] = Inventory(entries, ctx.graph.warnings.copy())
            return self.cache[category]


def collect(ctx: Context, category: str) -> list[Entry]:
    if category == "package":
        packages = ctx.packages.list_installed()
        if ctx.packages.problem:
            ctx.warning(ctx.packages.problem)
        return [
            Entry(category, pkg.name, f"package:{pkg.name}", f"{pkg.version}  {pkg.reason}")
            for pkg in packages
        ]
    if category == "unit":
        services, warnings = systemd.list_services(ctx.runner)
        for warning in warnings:
            ctx.warning(warning)
        return [
            Entry(category, name, f"unit:{name}", f"{active}  {enabled}")
            for name, active, enabled in services
        ]
    if category == "process":
        entries = []
        for pid in ctx.pids():
            if ctx.runner.cancelled():
                break
            try:
                process = procfs.process(ctx.fs, pid)
                entries.append(Entry(category, process.name, f"pid:{pid}", f"PID {pid}"))
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (OSError, ValueError, IndexError):
                ctx.warning("Some processes are inaccessible or changed during discovery")
        return entries
    if category == "socket":
        sockets = ctx.sockets()
        if not sockets:
            return []
        owners: dict[str, list[str]] = {}
        wanted = {sock.inode for sock in sockets}
        for pid in ctx.pids():
            if ctx.runner.cancelled():
                break
            try:
                before = procfs.process(ctx.fs, pid)
                matches = ctx.inodes(pid) & wanted
                if matches and procfs.process(ctx.fs, pid).start_time == before.start_time:
                    for inode in matches:
                        owners.setdefault(inode, []).append(f"{before.name} (PID {pid})")
            except (FileNotFoundError, ProcessLookupError):
                continue
            except (OSError, ValueError, IndexError):
                ctx.warning(
                    "Some socket ownership information is unavailable without elevated privileges"
                )
        endpoints: dict[str, set[str]] = {}
        for sock in sockets:
            address = f"[{sock.address}]" if ":" in sock.address else sock.address
            target = f"{sock.protocol}:{address}:{sock.port}"
            endpoints.setdefault(target, set()).update(owners.get(sock.inode, []))
        return [
            Entry(category, target, target, ", ".join(sorted(holders)) or "owner unknown")
            for target, holders in endpoints.items()
        ]
    if category == "interface":
        names: set[str] = set()
        try:
            names.update(ctx.fs.list("/sys/class/net"))
        except OSError:
            result = ctx.runner.run(["ip", "-j", "link", "show"])
            if result.code:
                ctx.warning(result.problem or "Interface inventory unavailable")
            else:
                records = json.loads(result.stdout)
                if not isinstance(records, list):
                    raise ValueError("Invalid ip link JSON") from None
                names.update(
                    str(row["ifname"])
                    for row in records
                    if isinstance(row, dict) and "ifname" in row
                )
        return [Entry(category, name, f"interface:{name}") for name in sorted(names)]
    if category == "module":
        names = set()
        try:
            names.update(ctx.fs.list("/sys/module"))
        except OSError:
            ctx.warning("Module sysfs inventory unavailable")
        try:
            names.update(
                line.split()[0]
                for line in ctx.fs.read("/proc/modules").splitlines()
                if line.split()
            )
        except OSError:
            ctx.warning("Loaded-module inventory unavailable; sysfs may include built-ins")
        return [Entry(category, name, f"module:{name}") for name in sorted(names)]
    if category == "file":
        entries = []
        seen = set()
        # Only existing executable PATH entries: never recursively walk the filesystem.
        for directory in os.get_exec_path():
            if not os.path.isabs(directory) or directory in seen:
                continue
            seen.add(directory)
            try:
                for name in ctx.fs.list(directory):
                    if ctx.runner.cancelled():
                        return entries
                    path = os.path.join(directory, name)
                    if ctx.fs.path(path).is_file() and os.access(ctx.fs.path(path), os.X_OK):
                        entries.append(Entry(category, path, f"file:{path}"))
            except OSError:
                ctx.warning("Some executable PATH directories are inaccessible")
        return entries
    raise ValueError(f"Unknown inventory category: {category}")
