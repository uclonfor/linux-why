import ipaddress
import json
import re
from collections.abc import Callable
from dataclasses import dataclass

from linux_why.backends import procfs, systemd
from linux_why.backends.packages.base import PackageBackend
from linux_why.core.models import Candidate
from linux_why.utils.command import Runner
from linux_why.utils.fs import FS

PREFIXES = {
    "package": "package",
    "file": "file",
    "pid": "process",
    "process": "process_name",
    "service": "unit",
    "unit": "unit",
    "interface": "interface",
    "module": "module",
}
UNIT_SUFFIXES = (
    ".service",
    ".socket",
    ".target",
    ".timer",
    ".mount",
    ".automount",
    ".swap",
    ".path",
    ".slice",
    ".scope",
    ".device",
)


@dataclass(frozen=True)
class PortQuery:
    port: int
    protocol: str | None = None
    address: str | None = None


def port_query(target: str) -> PortQuery:
    proto = None
    if target.startswith(("tcp:", "udp:")):
        proto, target = target.split(":", 1)
    host = None
    if ":" in target:
        raw_host, target = target.rsplit(":", 1)
        if raw_host:
            host = str(ipaddress.ip_address(raw_host.strip("[]")))
    if not target.isascii() or not target.isdecimal() or not 0 <= int(target) <= 65535:
        raise ValueError("Port must be an integer from 0 to 65535")
    return PortQuery(int(target), proto, host)


def validate(kind: str, value: str) -> str:
    if not value or any(ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Target must be nonempty and contain no control characters")
    if kind == "file":
        if not value.startswith("/"):
            raise ValueError("File targets must be absolute paths")
    elif kind == "process":
        if not re.fullmatch(r"[0-9]+", value) or not 0 < int(value) <= 2**31 - 1:
            raise ValueError("PID must be a positive 32-bit integer")
        value = str(int(value))
    elif kind == "package":
        if not re.fullmatch(r"[A-Za-z0-9@_+][A-Za-z0-9@_.+:\-]*", value):
            raise ValueError("Invalid package name (patterns are not accepted)")
    elif kind in ("module", "interface", "unit"):
        if "/" in value or value.startswith("-") or any(c in value for c in "*?[]"):
            raise ValueError(f"Invalid {kind} name")
        if kind == "module":
            if not re.fullmatch(r"[A-Za-z0-9_\-]+", value):
                raise ValueError("Invalid module name")
            value = value.replace("-", "_")
    return value


def detect(
    target: str,
    fs: FS,
    runner: Runner,
    packages: PackageBackend,
    warn: Callable[[str], None] | None = None,
) -> list[Candidate]:
    def unreadable(source: str) -> None:
        if warn:
            warn(f"Detection source unavailable: {source}")

    def processes(name: str) -> list[str]:
        try:
            return procfs.named_processes(fs, name)
        except OSError:
            unreadable("/proc")
            return []

    if not target or any(ord(c) < 32 or ord(c) == 127 for c in target):
        raise ValueError("Target must be nonempty and contain no control characters")
    prefix, separator, value = target.partition(":")
    if separator and prefix in PREFIXES:
        kind = PREFIXES[prefix]
        if not value:
            raise ValueError("Target after prefix must not be empty")
        if prefix == "service" and not value.endswith(UNIT_SUFFIXES):
            value += ".service"
        value = validate(kind, value)
        if kind == "process_name":
            return [
                Candidate("process", pid, f"process: {value} (PID {pid})")
                for pid in processes(value)
            ]
        return [Candidate(kind, value, f"{kind}: {value}")]
    if target.startswith((":", "tcp:", "udp:", "[")) or re.match(r"^\d+\.\d+\.\d+\.\d+:", target):
        port_query(target)
        return [Candidate("socket", target, target)]
    if target.startswith("/"):
        return [Candidate("file", target, target)]
    if target.isdecimal():
        return [Candidate("process", validate("process", target), f"PID {target}")]
    if target.endswith(UNIT_SUFFIXES):
        return [Candidate("unit", validate("unit", target), target)]
    candidates: list[Candidate] = []
    try:
        validate("package", target)
    except ValueError:
        pass
    else:
        pkg = packages.get(target)
        if pkg:
            candidates.append(Candidate("package", pkg.name, f"package: {pkg.name}"))
    executable = runner.which(target) if "/" not in target else None
    if executable:
        candidates.append(Candidate("file", executable, f"executable: {executable}"))
    for pid in processes(target):
        candidates.append(Candidate("process", pid, f"process: {target} (PID {pid})"))
    try:
        if "/" not in target and target in fs.list("/sys/class/net"):
            candidates.append(
                Candidate("interface", validate("interface", target), f"interface: {target}")
            )
    except FileNotFoundError:
        pass
    except OSError:
        unreadable("/sys/class/net")
        try:
            validate("interface", target)
            result = runner.run(["ip", "-j", "-d", "address", "show", "dev", target])
            records = json.loads(result.stdout) if result.code == 0 else []
            if isinstance(records, list) and any(
                isinstance(record, dict) and record.get("ifname") == target for record in records
            ):
                candidates.append(Candidate("interface", target, f"interface: {target}"))
        except ValueError:
            pass
    try:
        module = validate("module", target)
    except ValueError:
        module = ""
    if module:
        try:
            loaded = fs.exists(f"/sys/module/{module}")
        except OSError:
            unreadable(f"/sys/module/{module}")
            loaded = False
        if loaded or runner.run(["modinfo", "-F", "filename", "--", module]).code == 0:
            candidates.append(Candidate("module", module, f"module: {module}"))
    # A bare service name is an interpretation only if systemd confirms it exists.
    if re.fullmatch(r"[A-Za-z0-9_.@\-]+", target):
        data, result = systemd.show(runner, target + ".service")
        if result.code == 0 and data.get("LoadState") not in (None, "not-found"):
            candidates.append(Candidate("unit", target + ".service", f"unit: {target}.service"))
    return candidates
