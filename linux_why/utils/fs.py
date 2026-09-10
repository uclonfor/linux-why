"""Injectable, bounded Linux filesystem access. Paths remain Linux paths in fixtures."""

import os
from pathlib import Path


class FS:
    def __init__(self, root: Path = Path("/")) -> None:
        self.root = root

    def path(self, name: str) -> Path:
        return self.root / name.lstrip("/")

    def read(self, name: str, limit: int = 1_048_576) -> str:
        with self.path(name).open("rb") as stream:
            data = stream.read(limit + 1)
        if len(data) > limit:
            raise OSError(f"Read limit exceeded: {name}")
        return data.decode("utf-8", errors="replace")

    def tail(self, name: str, limit: int = 1_048_576) -> str:
        with self.path(name).open("rb") as stream:
            size = stream.seek(0, 2)
            stream.seek(max(0, size - limit))
            data = stream.read(limit)
        if size > limit:
            data = data.partition(b"\n")[2]
        return data.decode("utf-8", errors="replace")

    def exists(self, name: str) -> bool:
        try:
            self.path(name).stat()
            return True
        except FileNotFoundError:
            return False

    def lexists(self, name: str) -> bool:
        try:
            self.path(name).lstat()
            return True
        except FileNotFoundError:
            return False

    def list(self, name: str) -> list[str]:
        return sorted(p.name for p in self.path(name).iterdir())

    def link(self, name: str) -> str:
        return os.readlink(self.path(name))
