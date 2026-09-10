import pytest

from linux_why.backends.packages.base import Package, PackageBackend
from linux_why.utils.command import Result, Runner
from linux_why.utils.fs import FS


class FakeRunner(Runner):
    def __init__(self, responses=None, binaries=None):
        super().__init__()
        self.responses = responses or {}
        self.binaries = binaries or {}
        self.calls = []

    def which(self, name):
        return self.binaries.get(name)

    def run(self, args):
        self.calls.append(args)
        return self.responses.get(
            tuple(args), Result(127, problem=f"Optional command unavailable: {args[0]}")
        )


class FakePackages(PackageBackend):
    name = "fixture"

    def __init__(self, packages=None, owners=None):
        self.packages = packages or {}
        self.owners = owners or {}

    def get(self, name):
        return self.packages.get(name)

    def owner(self, path):
        return self.owners.get(path, [])


@pytest.fixture
def fs(tmp_path):
    fs = FS(tmp_path)
    put(fs, "/etc/os-release", "ID=arch\n")
    put(fs, "/etc/passwd", "test:x:1000:1000::/home/test:/bin/sh\n")
    fs.path("/proc").mkdir()
    for name in ("tcp", "tcp6", "udp", "udp6"):
        put(
            fs,
            f"/proc/net/{name}",
            "  sl  local_address rem_address st tx_queue rx_queue "
            "tr tm->when retrnsmt uid timeout inode\n",
        )
    return fs


def put(fs, name, data):
    path = fs.path(name)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(data)
    return path


def make_process(fs, pid, name="test", parent=0, exe=None, cgroup="0::/\n", start="100"):
    fields = ["S", str(parent)] + ["0"] * 17 + [start] + ["0"] * 5
    put(fs, f"/proc/{pid}/stat", f"{pid} ({name}) " + " ".join(fields))
    put(fs, f"/proc/{pid}/comm", name + "\n")
    put(fs, f"/proc/{pid}/cmdline", name + "\0--test\0")
    put(fs, f"/proc/{pid}/status", "Uid:\t1000\t1000\t1000\t1000\n")
    put(fs, f"/proc/{pid}/cgroup", cgroup)
    fs.path(f"/proc/{pid}/fd").mkdir(exist_ok=True)
    if exe:
        fs.path(f"/proc/{pid}/exe").symlink_to(exe)


def pkg(name, parents=(), reason="dependency"):
    return Package(name, "1.0", "pacman", reason, list(parents), evidence="fixture pacman -Qi")
