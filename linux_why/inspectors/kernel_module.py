import posixpath

from linux_why.core.graph import Context
from linux_why.core.models import Claim, Confidence, Node


def inspect(ctx: Context, name: str, depth: int) -> Node | None:
    base = f"/sys/module/{name}"
    present = ctx.fs.exists(base)
    result = ctx.runner.run(["modinfo", "-0", "--", name])
    if not present and result.code:
        if result.problem:
            ctx.warning(result.problem)
        return None
    node = ctx.graph.node("module", name, f"kernel module: {name}")
    loadable: bool | None = False
    try:
        for line in ctx.fs.read("/proc/modules").splitlines():
            fields = line.split()
            if fields and fields[0] == name:
                if len(fields) < 6:
                    raise ValueError("Malformed /proc/modules record")
                loadable = True
                node.attributes["reference_count"] = Claim(int(fields[2]), "/proc/modules")
                node.attributes["state"] = Claim(fields[4], "/proc/modules")
                break
    except (OSError, ValueError):
        loadable = None
        ctx.warning("Cannot read or parse /proc/modules")
    node.attributes["present_in_kernel"] = Claim(present, base)
    node.attributes["loaded_as_module"] = Claim(
        loadable, "/proc/modules", Confidence.UNKNOWN if loadable is None else Confidence.CONFIRMED
    )
    if result.code:
        ctx.warning(
            result.problem or "modinfo metadata unavailable (possibly built-in or different kernel)"
        )
    else:
        metadata: dict[str, list[str]] = {}
        for field in result.stdout.split("\0"):
            key, sep, value = field.partition(":")
            if sep:
                metadata.setdefault(key.strip(), []).append(value.strip())
        for key in ("filename", "description", "license", "version", "parm", "alias"):
            if key in metadata:
                node.attributes[key] = Claim(metadata[key], "modinfo -0")
        for filename in metadata.get("filename", []):
            if filename.startswith("/"):
                ctx.attach(
                    node,
                    "file",
                    filename,
                    "AVAILABLE_FROM",
                    "modinfo filename (module lookup)",
                    depth,
                )
        for dependency in metadata.get("depends", []):
            for dep in dependency.split(","):
                if dep:
                    ctx.attach(
                        node,
                        "module",
                        dep.replace("-", "_"),
                        "DEPENDS_ON",
                        "modinfo depends",
                        depth,
                    )
    if present:
        for folder, relation in (("holders", "USED_BY"), ("parameters", "")):
            try:
                entries = ctx.fs.list(f"{base}/{folder}")
            except FileNotFoundError:
                continue
            except OSError:
                ctx.warning(f"Cannot read {base}/{folder}")
                continue
            for entry in entries:
                if relation:
                    ctx.attach(node, "module", entry, relation, f"{base}/{folder}", depth)
                else:
                    try:
                        node.attributes[f"parameter.{entry}"] = Claim(
                            ctx.fs.read(f"{base}/{folder}/{entry}").strip(),
                            f"{base}/{folder}/{entry}",
                        )
                    except OSError:
                        ctx.warning(f"Module parameter unavailable: {entry}")
        try:
            drivers = ctx.fs.list(f"{base}/drivers")
        except FileNotFoundError:
            drivers = []
        for driver in drivers:
            driver_link = f"{base}/drivers/{driver}"
            target = ctx.fs.link(driver_link)
            path = posixpath.normpath(posixpath.join(posixpath.dirname(driver_link), target))
            for entry in ctx.fs.list(path):
                if entry in {
                    "module",
                    "subsystem",
                    "bind",
                    "unbind",
                    "uevent",
                    "new_id",
                    "remove_id",
                }:
                    continue
                try:
                    device_path = ctx.fs.link(f"{path}/{entry}")
                except OSError:
                    continue
                device_path = posixpath.normpath(posixpath.join(path, device_path))
                if len(ctx.graph.nodes) >= 250:
                    ctx.warning("Graph node budget reached")
                    break
                device = ctx.graph.node("device", device_path, f"device: {entry}")
                ctx.graph.link(node, device, "DRIVES", f"{path}/{entry}")
    return node
