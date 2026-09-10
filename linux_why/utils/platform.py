from linux_why.backends.packages.base import PackageBackend
from linux_why.backends.packages.dpkg import Dpkg
from linux_why.backends.packages.pacman import Pacman
from linux_why.utils.command import Runner
from linux_why.utils.fs import FS


def distribution(fs: FS) -> tuple[str, set[str]]:
    try:
        data = dict(
            line.split("=", 1)
            for line in fs.read("/etc/os-release").splitlines()
            if "=" in line and not line.startswith("#")
        )
    except OSError:
        data = {}
    name = data.get("ID", "unknown").strip("\"'")
    family = set(data.get("ID_LIKE", "").strip("\"'").split()) | {name}
    return name, family


def package_backend(fs: FS, runner: Runner) -> PackageBackend:
    name, family = distribution(fs)
    if "arch" in family:
        return Pacman(runner, fs)
    if family & {"debian", "ubuntu"}:
        return Dpkg(runner)
    backend = PackageBackend()
    backend.problem = f"Package provenance backend for {name} is not yet supported"
    return backend
