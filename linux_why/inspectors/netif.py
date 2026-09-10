import json
import posixpath

from linux_why.core.graph import Context
from linux_why.core.models import Claim, Confidence, Node


def inspect(ctx: Context, name: str, depth: int) -> Node | None:
    base = f"/sys/class/net/{name}"
    try:
        present = name in ctx.fs.list("/sys/class/net")
    except OSError:
        present = False
        ctx.warning("Interface sysfs unavailable; trying ip address data")
    result = ctx.runner.run(["ip", "-j", "-d", "address", "show", "dev", name])
    try:
        records = json.loads(result.stdout) if result.code == 0 else []
        if not isinstance(records, list) or any(not isinstance(record, dict) for record in records):
            raise ValueError("Invalid interface list")
    except ValueError:
        ctx.warning("Malformed ip JSON output")
        records = []
    info = next((record for record in records if record.get("ifname") == name), None)
    if not present and info is None:
        if result.problem:
            ctx.warning(result.problem)
        return None
    node = ctx.graph.node("interface", name, f"network interface: {name}")
    for attr in ("operstate", "address", "mtu", "ifindex", "type", "flags"):
        try:
            raw = ctx.fs.read(f"{base}/{attr}").strip()
            node.attributes[attr] = Claim(raw, f"{base}/{attr}")
            if attr == "flags":
                node.attributes["administrative_state"] = Claim(
                    "UP" if int(raw, 16) & 1 else "DOWN", f"{base}/flags"
                )
        except OSError:
            ctx.warning(f"Interface attribute unavailable: {base}/{attr}")
    for attr in ("master", "device/driver"):
        try:
            target = posixpath.basename(ctx.fs.link(f"{base}/{attr}"))
            node.attributes[attr] = Claim(target, f"readlink({base}/{attr})")
        except FileNotFoundError:
            pass
        except OSError:
            ctx.warning(f"Cannot read {base}/{attr}")
    if result.code:
        ctx.warning(result.problem or "ip could not query interface addresses")
    elif info is None:
        ctx.warning("Interface disappeared from ip address output")
    else:
        for key in (
            "addr_info",
            "link_type",
            "linkinfo",
            "master",
            "flags",
            "operstate",
            "mtu",
            "ifindex",
        ):
            if key in info:
                node.attributes[key] = Claim(info[key], "ip -j -d address show")
    node.attributes["creator"] = Claim(
        "not established", "sysfs/ip do not record historical creators", Confidence.UNKNOWN
    )
    # Interface names do not establish historical creators. No daemon is guessed.
    return node
