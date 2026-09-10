"""Small, serializable graph model. Facts carry evidence independently of edges."""

from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any


class Confidence(StrEnum):
    CONFIRMED = "confirmed"
    INFERRED = "inferred"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class Claim:
    value: Any
    source: str
    confidence: Confidence = Confidence.CONFIRMED


@dataclass
class Node:
    id: str
    type: str
    label: str
    attributes: dict[str, Claim] = field(default_factory=dict)


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    relation: str
    evidence: str
    confidence: Confidence = Confidence.CONFIRMED


@dataclass(frozen=True)
class Candidate:
    type: str
    value: str
    label: str

    @property
    def explicit_target(self) -> str:
        """Normalized resolver input, independent of human-facing labels.

        A property intentionally leaves the versioned JSON candidate shape intact.
        """
        if self.type == "socket":
            return self.value
        prefix = "pid" if self.type == "process" else self.type
        return f"{prefix}:{self.value}"


@dataclass
class Graph:
    target: str
    detected_type: str = "unknown"
    roots: list[str] = field(default_factory=list)
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: list[Edge] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    candidates: list[Candidate] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    partial: bool = False

    def warn(self, message: str, *, partial: bool = True) -> None:
        if message not in self.warnings:
            self.warnings.append(message)
        self.partial |= partial

    def node(self, kind: str, value: str, label: str | None = None) -> Node:
        key = f"{kind}:{value}"
        if key not in self.nodes:
            self.nodes[key] = Node(key, kind, label or f"{kind}: {value}")
        return self.nodes[key]

    def link(
        self,
        a: Node,
        b: Node,
        relation: str,
        evidence: str,
        confidence: Confidence = Confidence.CONFIRMED,
    ) -> None:
        edge = Edge(a.id, b.id, relation, evidence, confidence)
        if edge not in self.edges:
            self.edges.append(edge)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "1.0",
            "target": self.target,
            "detected_type": self.detected_type,
            "roots": self.roots,
            "nodes": [asdict(n) for n in self.nodes.values()],
            "edges": [asdict(e) for e in self.edges],
            "warnings": self.warnings,
            "partial": self.partial,
            "candidates": [asdict(c) for c in self.candidates],
            "metadata": self.metadata,
        }
