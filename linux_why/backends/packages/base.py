from dataclasses import dataclass, field


@dataclass
class Package:
    name: str
    version: str
    manager: str
    reason: str = "unknown"
    required_by: list[str] = field(default_factory=list)
    install_date: str | None = None
    evidence: str = ""
    warnings: list[str] = field(default_factory=list)
    log_event: str | None = None


class PackageBackend:
    name = "unsupported"
    problem: str | None = None

    def get(self, name: str) -> Package | None:
        return None

    def list_installed(self) -> list[Package]:
        """Inventory is opt-in for browsing, never used by single-target queries."""
        return []

    def owner(self, path: str) -> list[str]:
        return []
