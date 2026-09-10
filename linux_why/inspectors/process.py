from linux_why.backends import procfs
from linux_why.core.graph import Context
from linux_why.core.models import Claim, Node


def inspect(ctx: Context, pid: str, depth: int) -> Node | None:
    try:
        initial = procfs.process(ctx.fs, pid)
    except FileNotFoundError:
        return None
    node = ctx.graph.node("process", pid, f"{initial.name} (PID {pid})")
    node.attributes["pid"] = Claim(initial.pid, f"/proc/{pid}/stat")
    node.attributes["start_time_ticks"] = Claim(initial.start_time, f"/proc/{pid}/stat")
    # Read all identity-related fields before connecting to other subsystems.
    captured: dict[str, str] = {}
    for field, filename in {
        "command_line": "cmdline",
        "status": "status",
        "cgroup": "cgroup",
    }.items():
        try:
            captured[field] = ctx.fs.read(f"/proc/{pid}/{filename}")
        except OSError:
            ctx.warning(f"Process data unavailable: /proc/{pid}/{filename}")
    executable = ""
    try:
        executable = ctx.fs.link(f"/proc/{pid}/exe")
    except PermissionError:
        ctx.warning("Some ownership information is unavailable without elevated privileges")
    except FileNotFoundError:
        pass  # Kernel threads and zombies have no exe.
    try:
        final = procfs.process(ctx.fs, pid)
    except (OSError, ValueError):
        ctx.warning(f"Process {pid} disappeared during inspection")
        return node
    if final.start_time != initial.start_time:
        ctx.warning(f"PID {pid} was reused during inspection; cross-links discarded")
        return node
    if "command_line" in captured:
        node.attributes["command_line"] = Claim(
            captured["command_line"].rstrip("\0").split("\0") if captured["command_line"] else [],
            f"/proc/{pid}/cmdline",
        )
    if executable:
        node.attributes["executable"] = Claim(executable, f"/proc/{pid}/exe")
        if not executable.endswith(" (deleted)"):
            try:
                same_mount = ctx.fs.link(f"/proc/{pid}/ns/mnt") == ctx.fs.link("/proc/self/ns/mnt")
            except OSError:
                same_mount = False
            if same_mount:
                ctx.attach(node, "file", executable, "EXECUTES", f"/proc/{pid}/exe", depth)
            else:
                ctx.warning(
                    f"Process {pid} mount namespace differs or is unreadable; "
                    "host file/package ownership not attributed"
                )
    uid = next(
        (
            line.split()[1]
            for line in captured.get("status", "").splitlines()
            if line.startswith("Uid:") and len(line.split()) >= 2
        ),
        None,
    )
    if uid and uid.isdecimal():
        # pwd may invoke network-backed NSS; use local /etc/passwd exclusively.
        username = uid
        try:
            for line in ctx.fs.read("/etc/passwd").splitlines():
                parts = line.split(":")
                if len(parts) >= 7 and parts[2] == uid:
                    username = parts[0]
                    break
        except OSError:
            pass
        node.attributes["user"] = Claim(
            f"{username} (UID {uid})", f"/proc/{pid}/status; /etc/passwd"
        )
    unit = procfs.owning_unit(captured.get("cgroup", ""))
    if unit:
        # User-manager units require a different bus. Membership remains a fact,
        # but do not query the system manager for a same-named user service.
        node.attributes["systemd_cgroup_unit"] = Claim(unit, f"/proc/{pid}/cgroup")
        if not any(
            part.startswith("user@") and part.endswith(".service")
            for part in captured.get("cgroup", "").split("/")
        ):
            ctx.attach(node, "unit", unit, "MEMBER_OF", f"/proc/{pid}/cgroup", depth)
    if initial.parent > 0 and initial.parent != initial.pid:
        ctx.attach(node, "process", str(initial.parent), "CHILD_OF", f"/proc/{pid}/stat", depth)
    if depth == 0:
        try:
            inodes = ctx.inodes(pid)
            from linux_why.inspectors.socket import socket_node

            for sock in ctx.sockets():
                if sock.inode in inodes:
                    child = socket_node(ctx, sock)
                    ctx.graph.link(node, child, "LISTENS_ON", f"/proc/{pid}/fd; {sock.source}")
        except PermissionError:
            ctx.warning("Some ownership information is unavailable without elevated privileges")
        except FileNotFoundError:
            ctx.warning(f"Process {pid} disappeared during socket inspection")
    return node
