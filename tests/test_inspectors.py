import json

import pytest
from conftest import FakePackages, FakeRunner, make_process, pkg, put

from linux_why.backends import procfs
from linux_why.backends.systemd import PROPERTIES
from linux_why.core.graph import Context
from linux_why.utils.command import Result


def context(fs, **kw):
    return Context(
        "test",
        fs=fs,
        runner=kw.get("runner", FakeRunner()),
        packages=kw.get("packages", FakePackages()),
    )


def test_ancestry(fs):
    make_process(fs, 42, "name (with) parentheses", parent=41)
    make_process(fs, 41, "sh")
    ctx = context(fs)
    node = ctx.expand("process", "42")
    assert "name (with) parentheses" in node.label
    assert any(e.relation == "CHILD_OF" and e.target == "process:41" for e in ctx.graph.edges)
    assert node.attributes["user"].value == "test (UID 1000)"


def test_malformed_stat(fs):
    put(fs, "/proc/42/stat", "42 (bad) S")
    ctx = context(fs)
    assert ctx.expand("process", "42") is None
    assert ctx.graph.partial


def test_disappeared(fs):
    ctx = context(fs)
    assert ctx.expand("process", "999") is None
    assert not ctx.graph.partial


def test_permission_denied(fs, monkeypatch):
    make_process(fs, 42)
    original = fs.read

    def read(path, *args):
        if path.endswith("status"):
            raise PermissionError(path)
        return original(path, *args)

    monkeypatch.setattr(fs, "read", read)
    ctx = context(fs)
    assert ctx.expand("process", "42")
    assert ctx.graph.partial


def test_pid_reuse(fs, monkeypatch):
    make_process(fs, 42)
    original = fs.read
    calls = 0

    def read(path, *args):
        nonlocal calls
        text = original(path, *args)
        if path.endswith("/stat"):
            calls += 1
            if calls > 1:
                return text.replace("100", "200")
        return text

    monkeypatch.setattr(fs, "read", read)
    ctx = context(fs)
    ctx.expand("process", "42")
    assert ctx.graph.partial
    assert not ctx.graph.edges


@pytest.mark.parametrize(
    ("text", "unit"),
    [
        ("0::/system.slice/sshd.service\n", "sshd.service"),
        ("1:name=systemd:/user.slice/session-4.scope\n", "session-4.scope"),
        ("2:cpu:/fake.service\n", None),
    ],
)
def test_cgroup(text, unit):
    assert procfs.owning_unit(text) == unit


def test_symlink_chain(fs):
    put(fs, "/usr/bin/real", "test")
    fs.path("/usr/bin/link").symlink_to("real")
    ctx = context(fs, packages=FakePackages({"tool": pkg("tool")}, {"/usr/bin/real": ["tool"]}))
    ctx.expand("file", "/usr/bin/link")
    assert {e.relation for e in ctx.graph.edges} == {"SYMLINK_TO", "OWNED_BY"}


def test_symlink_loop(fs):
    fs.path("/a").symlink_to("b")
    fs.path("/b").symlink_to("a")
    ctx = context(fs)
    ctx.expand("file", "/a")
    assert len(ctx.graph.nodes) == 2
    assert any("cycle" in w for w in ctx.graph.warnings)


def test_dangling(fs):
    fs.path("/a").symlink_to("/missing")
    assert context(fs).expand("file", "/a").attributes["dangling"].value


def test_systemd(fs):
    args = (
        "systemctl",
        "--no-pager",
        "--no-ask-password",
        "show",
        "--property=" + ",".join(PROPERTIES),
        "--",
        "sshd.service",
    )
    output = (
        "Id=sshd.service\n"
        "LoadState=loaded\n"
        "ActiveState=active\n"
        "UnitFileState=enabled\n"
        "MainPID=42\n"
        "FragmentPath=/usr/lib/systemd/system/sshd.service\n"
        "TriggeredBy=sshd.socket\n"
    )
    socket_args = (*args[:-1], "sshd.socket")
    runner = FakeRunner(
        {args: Result(0, output), socket_args: Result(0, "Id=sshd.socket\nLoadState=loaded\n")}
    )
    make_process(fs, 42, "sshd", cgroup="0::/system.slice/sshd.service\n")
    put(fs, "/usr/lib/systemd/system/sshd.service", "[Service]\nExecStart=/usr/bin/sshd\n")
    ctx = context(fs, runner=runner)
    ctx.expand("unit", "sshd.service")
    relations = {e.relation for e in ctx.graph.edges}
    assert {"MAIN_PROCESS", "DEFINED_BY", "MEMBER_OF", "TRIGGERED_BY"} <= relations
    assert "STARTS" not in relations


def test_netif_no_creator_guess(fs):
    for key, value in {
        "operstate": "up",
        "address": "00:00:00:00:00:00",
        "mtu": "1500",
        "ifindex": "2",
        "type": "1",
        "flags": "0x1003",
    }.items():
        put(fs, f"/sys/class/net/docker0/{key}", value)
    data = [{"ifname": "docker0", "linkinfo": {"info_kind": "bridge"}, "addr_info": []}]
    runner = FakeRunner(
        {("ip", "-j", "-d", "address", "show", "dev", "docker0"): Result(0, json.dumps(data))}
    )
    ctx = context(fs, runner=runner)
    node = ctx.expand("interface", "docker0")
    assert node.attributes["administrative_state"].value == "UP"
    assert not ctx.graph.edges
    assert not ctx.graph.partial


def test_module(fs):
    put(fs, "/proc/modules", "test 123 1 other, Live 0x000\n")
    put(fs, "/sys/module/test/parameters/foo", "1")
    data = "filename: /usr/lib/modules/test.ko\0depends: \0parm: foo:an option\0"
    put(fs, "/usr/lib/modules/test.ko", "")
    ctx = context(fs, runner=FakeRunner({("modinfo", "-0", "--", "test"): Result(0, data)}))
    node = ctx.expand("module", "test")
    assert node.attributes["loaded_as_module"].value
    assert node.attributes["parameter.foo"].value == "1"
    assert node.attributes["filename"].value == ["/usr/lib/modules/test.ko"]


def test_namespace_mismatch_does_not_attribute_host_package(fs):
    make_process(fs, 42, exe="/usr/bin/tool")
    put(fs, "/usr/bin/tool", "test")
    fs.path("/proc/42/ns").mkdir()
    fs.path("/proc/self/ns").mkdir(parents=True)
    fs.path("/proc/42/ns/mnt").symlink_to("mnt:[2]")
    fs.path("/proc/self/ns/mnt").symlink_to("mnt:[1]")
    ctx = context(fs)
    ctx.expand("process", "42")
    assert not any(e.relation == "EXECUTES" for e in ctx.graph.edges)
    assert ctx.graph.partial


def test_unreadable_module_load_state_is_unknown(fs, monkeypatch):
    fs.path("/sys/module/test").mkdir(parents=True)
    original = fs.read

    def read(path, *args):
        if path == "/proc/modules":
            raise PermissionError(path)
        return original(path, *args)

    monkeypatch.setattr(fs, "read", read)
    ctx = context(fs)
    node = ctx.expand("module", "test")
    claim = node.attributes["loaded_as_module"]
    assert claim.value is None
    assert claim.confidence == "unknown"


def test_unit_not_found_nonzero_exit(fs):
    args = (
        "systemctl",
        "--no-pager",
        "--no-ask-password",
        "show",
        "--property=" + ",".join(PROPERTIES),
        "--",
        "missing.service",
    )
    ctx = context(fs, runner=FakeRunner({args: Result(4, "LoadState=not-found\n")}))
    assert ctx.expand("unit", "missing.service") is None
    assert not ctx.graph.partial


def test_netif_ip_fallback(fs, monkeypatch):
    original = fs.list

    def listing(path):
        if path == "/sys/class/net":
            raise PermissionError(path)
        return original(path)

    monkeypatch.setattr(fs, "list", listing)
    runner = FakeRunner(
        {
            ("ip", "-j", "-d", "address", "show", "dev", "lo"): Result(
                0, '[{"ifname":"lo","link_type":"loopback"}]'
            )
        }
    )
    ctx = context(fs, runner=runner)
    node = ctx.expand("interface", "lo")
    assert node.attributes["link_type"].value == "loopback"
    assert ctx.graph.partial


def test_malformed_ip_preserves_partial_node(fs):
    fs.path("/sys/class/net/lo").mkdir(parents=True)
    runner = FakeRunner(
        {("ip", "-j", "-d", "address", "show", "dev", "lo"): Result(0, "{not json}")}
    )
    ctx = context(fs, runner=runner)
    assert ctx.expand("interface", "lo") is not None
    assert ctx.graph.partial


def test_missing_file(fs):
    ctx = context(fs)
    assert ctx.expand("file", "/missing") is None
    assert not ctx.graph.partial
