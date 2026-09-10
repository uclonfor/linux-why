"""Plain tree rendering with optional ANSI color and terminal-control sanitization."""

import json

from linux_why.core.models import Graph


def safe(text: str) -> str:
    return "".join(c if c.isprintable() else repr(c)[1:-1] for c in text)


def render(graph: Graph, *, verbose: bool = False, color: bool = False) -> str:
    lines: list[str] = []
    if graph.candidates:
        lines.append("Multiple interpretations found:")
        for index, candidate in enumerate(graph.candidates, 1):
            lines.append(f"{index}. {safe(candidate.label)}")
        lines.append(
            "Choose an explicit target: "
            + ", ".join(
                safe(f"{('pid' if c.type == 'process' else c.type)}:{c.value}")
                for c in graph.candidates
            )
        )
        return "\n".join(lines)
    outgoing: dict[str, list[tuple[str, str]]] = {}
    for edge in graph.edges:
        relation = edge.relation.lower().replace("_", " ")
        suffix = f" [{edge.confidence}]" if edge.confidence != "confirmed" else ""
        if verbose:
            suffix = f" [{edge.confidence}; {safe(edge.evidence)}]"
        outgoing.setdefault(edge.source, []).append((edge.target, relation + suffix))
    seen: set[str] = set()

    def visit(key: str, prefix: str, branch: str, relation: str = "") -> None:
        node = graph.nodes[key]
        label = safe(node.label)
        if color:
            label = f"\033[36m{label}\033[0m"
        lines.append(
            prefix
            + branch
            + (relation + ": " if relation else "")
            + label
            + (" (already shown)" if key in seen else "")
        )
        if key in seen:
            return
        seen.add(key)
        indent = prefix + ("   " if branch == "└─ " else "│  " if branch else "")
        items: list[tuple[str, str, bool]] = []
        for attr, claim in node.attributes.items():
            if not verbose and attr in {
                "start_time_ticks",
                "inode",
                "pid",
                "After",
                "Names",
                "alias",
            }:
                continue
            value = (
                claim.value
                if isinstance(claim.value, str)
                else json.dumps(claim.value, ensure_ascii=True)
            )
            suffix = f" [{claim.confidence}]" if claim.confidence != "confirmed" else ""
            if verbose:
                suffix = f" [{claim.confidence}; {safe(claim.source)}]"
            items.append((safe(attr.replace("_", " ")) + ": " + safe(value) + suffix, "", False))
        items.extend((child, rel, True) for child, rel in outgoing.get(key, []))
        for index, (value, rel, is_node) in enumerate(items):
            twig = "└─ " if index == len(items) - 1 else "├─ "
            if is_node:
                visit(value, indent, twig, rel)
            else:
                lines.append(indent + twig + value)

    for root in graph.roots:
        visit(root, "", "")
    if not graph.roots:
        lines.append(f'Could not determine what "{safe(graph.target)}" refers to.')
        lines.append(
            "Possible target types: package, process/PID, file, unit, socket, interface, module"
        )
        lines.append(f"Try: linux-why package:{safe(graph.target)}")
    lines.extend("Warning: " + safe(warning) for warning in graph.warnings)
    return "\n".join(lines)
