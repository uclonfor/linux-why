"""Query-scoped expansion with caching, cycle protection and bounded work."""

from collections.abc import Callable

from linux_why import __version__
from linux_why.backends import procfs
from linux_why.backends.packages.base import PackageBackend
from linux_why.core.models import Claim, Confidence, Graph, Node
from linux_why.utils.command import Runner
from linux_why.utils.fs import FS
from linux_why.utils.platform import distribution, package_backend

Inspector = Callable[["Context", str, int], Node | None]


class Context:
    def __init__(
        self,
        target: str,
        depth: int = 5,
        *,
        fs: FS | None = None,
        runner: Runner | None = None,
        packages: PackageBackend | None = None,
    ) -> None:
        self.fs = fs or FS()
        self.runner = runner or Runner()
        self.packages = packages or package_backend(self.fs, self.runner)
        self.depth = depth
        self.graph = Graph(
            target,
            metadata={
                "platform": distribution(self.fs)[0],
                "version": __version__,
                "max_depth": depth,
                "network_namespace": "current",
                "max_nodes": 250,
            },
        )
        self.expanded: dict[tuple[str, str], int] = {}
        self.socket_cache: list[procfs.Socket] | None = None
        self.pid_cache: list[str] | None = None

    def warning(self, message: str) -> None:
        self.graph.warn(message)

    def expand(self, kind: str, value: str, depth: int = 0) -> Node | None:
        from linux_why.inspectors import INSPECTORS

        if self.runner.cancelled():
            return None
        key = (kind, value)
        if key in self.expanded and self.expanded[key] <= depth:
            return self.graph.nodes.get(f"{kind}:{value}")
        if depth > self.depth:
            self.graph.warn("Depth limit reached; increase --depth for more context", partial=False)
            return None
        if len(self.graph.nodes) >= 250:
            self.warning("Graph node budget reached")
            return None
        self.expanded[key] = depth
        try:
            return INSPECTORS[kind](self, value, depth)
        except PermissionError:
            self.warning(f"Permission denied while inspecting {kind}: {value}")
        except FileNotFoundError:
            self.warning(f"Object disappeared or data source unavailable: {kind}: {value}")
        except (OSError, ValueError, IndexError) as exc:
            self.warning(f"Cannot fully inspect {kind}: {value}: {exc}")
        return self.graph.nodes.get(f"{kind}:{value}")

    def attach(
        self, node: Node, kind: str, value: str, relation: str, evidence: str, depth: int
    ) -> Node | None:
        child = self.expand(kind, value, depth + 1)
        if child:
            self.graph.link(node, child, relation, evidence)
        return child

    def own(self, node: Node, path: str, depth: int) -> None:
        owners = self.packages.owner(path)
        if self.packages.problem:
            self.warning(self.packages.problem)
        node.attributes["package_ownership"] = Claim(
            owners or "not recorded" if not self.packages.problem else "unknown",
            f"{self.packages.name} ownership query",
            Confidence.UNKNOWN if self.packages.problem else Confidence.CONFIRMED,
        )
        for owner in owners:
            self.attach(
                node, "package", owner, "OWNED_BY", f"{self.packages.name} ownership query", depth
            )

    def pids(self) -> list[str]:
        if self.pid_cache is None:
            self.pid_cache = procfs.pids(self.fs)
        return self.pid_cache

    def sockets(self) -> list[procfs.Socket]:
        if self.socket_cache is None:
            self.socket_cache = []
            for table in ("tcp", "tcp6", "udp", "udp6"):
                path = f"/proc/net/{table}"
                try:
                    records, malformed = procfs.parse_sockets(self.fs.read(path), table[:3], path)
                    self.socket_cache.extend(records)
                    if malformed:
                        self.warning(f"Malformed socket records skipped: {path}")
                except FileNotFoundError:
                    if not table.endswith("6"):
                        self.warning(f"Socket table unavailable: {path}")
                except OSError:
                    self.warning(f"Cannot read socket table: {path}")
        return self.socket_cache

    def inodes(self, pid: str) -> set[str]:
        result: set[str] = set()
        for fd in self.fs.list(f"/proc/{pid}/fd"):
            try:
                link = self.fs.link(f"/proc/{pid}/fd/{fd}")
                if link.startswith("socket:[") and link.endswith("]"):
                    result.add(link[8:-1])
            except FileNotFoundError:
                continue
        return result
