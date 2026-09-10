import re

from linux_why.backends.systemd import show
from linux_why.core.graph import Context
from linux_why.core.models import Claim, Node


def inspect(ctx: Context, name: str, depth: int) -> Node | None:
    data, result = show(ctx.runner, name)
    if data.get("LoadState") == "not-found":
        return None
    if result.code:
        ctx.warning(result.problem or f"systemd manager unavailable: {result.stderr.strip()}")
        return None
    if not data.get("Id") or not data.get("LoadState"):
        ctx.warning("Malformed systemctl show output")
        return None
    node = ctx.graph.node("unit", name, name)
    node.attributes["type"] = Claim(name.rsplit(".", 1)[-1], "unit name")
    for prop in (
        "Id",
        "Names",
        "LoadState",
        "ActiveState",
        "SubState",
        "UnitFileState",
        "MainPID",
        "ExecStart",
        "FragmentPath",
        "DropInPaths",
        "After",
    ):
        if data.get(prop):
            node.attributes[prop] = Claim(data[prop], "systemctl show")
    for prop, relation in {
        "Requires": "REQUIRES",
        "Wants": "WANTS",
        "Requisite": "REQUISITE",
        "BindsTo": "BINDS_TO",
        "RequiredBy": "REQUIRED_BY",
        "WantedBy": "WANTED_BY",
        "TriggeredBy": "TRIGGERED_BY",
        "Triggers": "TRIGGERS",
        "PartOf": "PART_OF",
    }.items():
        for unit in data.get(prop, "").split():
            ctx.attach(node, "unit", unit, relation, f"systemctl show {prop}", depth)
    if data.get("FragmentPath"):
        ctx.attach(
            node, "file", data["FragmentPath"], "DEFINED_BY", "systemctl show FragmentPath", depth
        )
    # Escaped paths are retained verbatim in claims rather than incorrectly split.
    for path in data.get("DropInPaths", "").split():
        if path.startswith("/") and "\\" not in path:
            ctx.attach(node, "file", path, "CONFIGURED_BY", "systemctl show DropInPaths", depth)
    pid = data.get("MainPID", "0")
    if pid.isdecimal() and int(pid) > 0:
        ctx.attach(node, "process", pid, "MAIN_PROCESS", "systemctl show MainPID", depth)
    for path in re.findall(r"(?:^|\{ )path=([^ ;]+)", data.get("ExecStart", "")):
        if path.startswith("/") and "\\" not in path:
            ctx.attach(
                node, "file", path, "CONFIGURED_TO_EXECUTE", "systemctl show ExecStart", depth
            )
    return node
