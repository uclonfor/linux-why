"""Shared entry point for direct CLI and interactive explanations."""

from linux_why.core.detector import detect
from linux_why.core.graph import Context


def resolve(ctx: Context) -> int:
    candidates = detect(ctx.graph.target, ctx.fs, ctx.runner, ctx.packages, ctx.warning)
    if len(candidates) > 1:
        ctx.graph.candidates = candidates
        ctx.graph.detected_type = "ambiguous"
        return 2
    if candidates:
        candidate = candidates[0]
        ctx.graph.detected_type = candidate.type
        node = ctx.expand(candidate.type, candidate.value)
        if node:
            ctx.graph.roots.append(node.id)
    elif ctx.packages.problem:
        ctx.warning(ctx.packages.problem)
    return 3 if ctx.graph.partial else (0 if ctx.graph.roots else 1)
