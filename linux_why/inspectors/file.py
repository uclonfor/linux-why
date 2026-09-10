import posixpath
import stat

from linux_why.core.graph import Context
from linux_why.core.models import Claim, Node


def inspect(ctx: Context, path: str, depth: int) -> Node | None:
    try:
        status = ctx.fs.path(path).lstat()
    except FileNotFoundError:
        return None
    node = ctx.graph.node("file", path, path)
    kind = (
        "symlink"
        if stat.S_ISLNK(status.st_mode)
        else (
            "directory"
            if stat.S_ISDIR(status.st_mode)
            else ("regular file" if stat.S_ISREG(status.st_mode) else "special file")
        )
    )
    node.attributes["type"] = Claim(kind, f"lstat({path})")
    ctx.own(node, path, depth)
    if kind == "symlink":
        destination = ctx.fs.link(path)
        target = posixpath.normpath(posixpath.join(posixpath.dirname(path), destination))
        node.attributes["link_target"] = Claim(destination, f"readlink({path})")
        if ("file", target) in ctx.expanded:
            ctx.graph.warn(f"Symlink cycle or previously visited target: {target}", partial=False)
        elif ctx.fs.lexists(target):
            ctx.attach(node, "file", target, "SYMLINK_TO", f"readlink({path})", depth)
        else:
            node.attributes["dangling"] = Claim(True, f"lstat({target})")
    # Only direct file queries scan executable users; recursive file nodes stay cheap.
    if depth == 0 and stat.S_ISREG(status.st_mode) and status.st_mode & 0o111:
        inaccessible = False
        for pid in ctx.pids():
            try:
                if ctx.fs.link(f"/proc/{pid}/exe") == path:
                    child = ctx.expand("process", pid, depth + 1)
                    if (
                        child
                        and child.attributes.get("executable") == Claim(path, f"/proc/{pid}/exe")
                        and ctx.fs.link(f"/proc/{pid}/ns/mnt") == ctx.fs.link("/proc/self/ns/mnt")
                    ):
                        ctx.graph.link(node, child, "EXECUTED_BY", f"/proc/{pid}/exe")
            except PermissionError:
                inaccessible = True
            except OSError:
                continue
        if inaccessible:
            ctx.warning("Some executable users are unavailable without elevated privileges")
    return node
