from linux_why.backends.procfs import Socket, process
from linux_why.core.detector import port_query
from linux_why.core.graph import Context
from linux_why.core.models import Claim, Node


def socket_node(ctx: Context, sock: Socket) -> Node:
    host = f"[{sock.address}]" if ":" in sock.address else sock.address
    identity = f"{sock.protocol}:{host}:{sock.port}:{sock.inode}"
    node = ctx.graph.node("socket", identity, f"{sock.protocol.upper()} {host}:{sock.port}")
    for key, value in {
        "protocol": sock.protocol,
        "bind_address": sock.address,
        "port": sock.port,
        "inode": sock.inode,
    }.items():
        node.attributes[key] = Claim(value, sock.source)
    return node


def inspect(ctx: Context, value: str, depth: int) -> Node | None:
    query = port_query(value)
    matches = [
        sock
        for sock in ctx.sockets()
        if sock.port == query.port
        and (query.protocol is None or sock.protocol == query.protocol)
        and (query.address is None or sock.address == query.address)
    ]
    if not matches:
        return None
    root = ctx.graph.node("socket", value, f"Listening/bound sockets: {value}")
    available = max(0, 250 - len(ctx.graph.nodes))
    if len(matches) > available:
        ctx.warning("Graph node budget reached")
    nodes = [(sock, socket_node(ctx, sock)) for sock in matches[:available]]
    for sock, node in nodes:
        ctx.graph.link(root, node, "MATCHES", sock.source)
    by_inode = {sock.inode for sock in matches}
    found: set[str] = set()
    inaccessible = False
    for pid in ctx.pids():
        try:
            initial = process(ctx.fs, pid)
            inodes = ctx.inodes(pid) & by_inode
            if not inodes:
                continue
            final = process(ctx.fs, pid)
            if initial.start_time != final.start_time:
                ctx.warning(f"PID {pid} reused while resolving socket ownership")
                continue
            child = ctx.expand("process", pid, depth + 1)
            if child:
                identity = child.attributes.get("start_time_ticks")
                if identity is None or identity.value != initial.start_time:
                    ctx.warning(f"PID {pid} identity changed; socket cross-link discarded")
                    continue
                for sock, node in nodes:
                    if sock.inode in inodes:
                        ctx.graph.link(node, child, "HELD_BY", f"/proc/{pid}/fd; {sock.source}")
                        found.add(sock.inode)
        except PermissionError:
            inaccessible = True
        except (FileNotFoundError, ProcessLookupError):
            continue
        except (OSError, ValueError, IndexError):
            ctx.warning("Some process data was malformed or unavailable during socket lookup")
    if inaccessible:
        ctx.warning("Some ownership information is unavailable without elevated privileges")
    if by_inode - found:
        ctx.warning(
            "Some socket owners could not be resolved "
            "(permissions, kernel ownership or process exit)"
        )
    return root
