import os
import shutil
import socket
import sys

import pytest

from linux_why.backends import procfs
from linux_why.core.graph import Context
from linux_why.utils.fs import FS

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "linux", reason="Linux only"),
]


def test_real_self():
    if not os.path.exists("/proc/self/stat"):
        pytest.skip("procfs unavailable")
    assert procfs.process(FS(), str(os.getpid())).pid == os.getpid()


def test_real_loopback():
    if not os.path.exists("/sys/class/net/lo") and not shutil.which("ip"):
        pytest.skip("no loopback sysfs")
    ctx = Context("lo")
    node = ctx.expand("interface", "lo")
    assert node is not None
    assert node.attributes["ifindex"].value


def test_real_local_listener():
    if not os.path.exists("/proc/net/tcp"):
        pytest.skip("no proc socket table")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        ctx = Context(f"tcp:{port}", depth=1)
        assert ctx.expand("socket", f"tcp:{port}") is not None
        assert any(
            e.relation == "HELD_BY" and e.target == f"process:{os.getpid()}"
            for e in ctx.graph.edges
        )


def test_real_arch_package():
    ctx = Context("package:pacman", depth=0)
    if ctx.packages.name != "pacman" or not ctx.runner.which("pacman"):
        pytest.skip("requires Arch and pacman")
    node = ctx.expand("package", "pacman")
    assert node and node.attributes["package_manager"].value == "pacman"
