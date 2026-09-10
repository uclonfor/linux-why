import ipaddress
import sys
from dataclasses import dataclass

from linux_why.utils.fs import FS


@dataclass(frozen=True)
class Process:
    pid: int
    name: str
    parent: int
    start_time: str


def process(fs: FS, pid: str) -> Process:
    text = fs.read(f"/proc/{pid}/stat")
    left, right = text.index("("), text.rindex(")")
    fields = text[right + 2 :].split()
    if len(fields) < 20 or int(text[:left].strip()) != int(pid):
        raise ValueError("Malformed process stat")
    return Process(int(pid), text[left + 1 : right], int(fields[1]), fields[19])


def pids(fs: FS) -> list[str]:
    return [name for name in fs.list("/proc") if name.isdecimal()]


def named_processes(fs: FS, name: str) -> list[str]:
    matches = []
    for pid in pids(fs):
        try:
            if fs.read(f"/proc/{pid}/comm").strip() == name:
                matches.append(pid)
        except OSError:
            continue  # An inaccessible name cannot establish a match.
    return matches


def owning_unit(text: str) -> str | None:
    for line in text.splitlines():
        parts = line.split(":", 2)
        if len(parts) == 3 and (parts[0] == "0" or "name=systemd" in parts[1].split(",")):
            for component in reversed(parts[2].split("/")):
                if component.endswith((".service", ".scope")):
                    return component
    return None


@dataclass(frozen=True)
class Socket:
    protocol: str
    address: str
    port: int
    inode: str
    source: str


def address(raw: str) -> str:
    data = bytes.fromhex(raw)
    if len(data) not in (4, 16):
        raise ValueError("Invalid socket address length")
    if sys.byteorder == "little":
        data = b"".join(data[i : i + 4][::-1] for i in range(0, len(data), 4))
    return str(ipaddress.ip_address(data))


def parse_sockets(text: str, protocol: str, source: str) -> tuple[list[Socket], bool]:
    result = []
    malformed = False
    for line in text.splitlines()[1:]:
        if not line.strip():
            continue
        try:
            fields = line.split()
            if len(fields) < 10:
                raise ValueError("Short socket record")
            if fields[3] != ("0A" if protocol == "tcp" else "07"):
                continue
            host, port = fields[1].split(":")
            value = int(port, 16)
            if not 0 <= value <= 65535 or not fields[9].isdecimal():
                raise ValueError("Invalid socket port/inode")
            result.append(Socket(protocol, address(host), value, fields[9], source))
        except (ValueError, IndexError):
            malformed = True
    return result, malformed
