from linux_why.core.graph import Context
from linux_why.core.models import Claim, Confidence, Node


def inspect(ctx: Context, name: str, depth: int) -> Node | None:
    pkg = ctx.packages.get(name)
    if ctx.packages.problem:
        ctx.warning(ctx.packages.problem)
    if pkg is None:
        return None
    node = ctx.graph.node("package", name)
    for key, value in {
        "version": pkg.version,
        "package_manager": pkg.manager,
        "install_reason": pkg.reason,
    }.items():
        node.attributes[key] = Claim(
            value, pkg.evidence, Confidence.UNKNOWN if value == "unknown" else Confidence.CONFIRMED
        )
    if pkg.install_date:
        node.attributes["last_install_date"] = Claim(pkg.install_date, pkg.evidence)
    if pkg.log_event:
        node.attributes["recent_install_log_event"] = Claim(
            pkg.log_event, "/var/log/pacman.log (last 1 MiB)"
        )
    for warning in pkg.warnings:
        ctx.warning(warning)
    for parent in pkg.required_by:
        ctx.attach(node, "package", parent, "REQUIRED_BY", pkg.evidence, depth)
    return node
