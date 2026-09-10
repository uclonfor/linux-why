import sys

import pytest
from conftest import FakePackages, FakeRunner, make_process, put

from linux_why.backends.procfs import parse_sockets
from linux_why.core.graph import Context


def row(host="0100007F", port="0016", state="0A", inode="123"):
    return (
        f" 0: {host}:{port} 00000000:0000 {state} "
        f"00000000:00000000 00:00000000 00000000 1000 0 {inode} 1\n"
    )


@pytest.mark.skipif(sys.byteorder != "little", reason="little-endian proc fixture")
def test_tcp():
    records, bad = parse_sockets("header\n" + row(), "tcp", "fixture")
    assert not bad
    assert (records[0].address, records[0].port, records[0].inode) == ("127.0.0.1", 22, "123")


def test_filter_connected():
    assert parse_sockets("header\n" + row(state="01"), "tcp", "fixture")[0] == []
    assert parse_sockets("header\n" + row(state="01"), "udp", "fixture")[0] == []
    assert len(parse_sockets("header\n" + row(state="07"), "udp", "fixture")[0]) == 1


@pytest.mark.skipif(sys.byteorder != "little", reason="little-endian proc fixture")
def test_ipv6():
    records, _ = parse_sockets(
        "header\n" + row(host="00000000000000000000000001000000"), "tcp", "fixture"
    )
    assert records[0].address == "::1"


def test_malformed():
    assert parse_sockets("header\ninvalid\n", "tcp", "fixture") == ([], True)


def test_ownership(fs):
    put(fs, "/proc/net/tcp", "header\n" + row())
    make_process(fs, 42, "sshd")
    fs.path("/proc/42/fd/3").symlink_to("socket:[123]")
    ctx = Context(":22", fs=fs, runner=FakeRunner(), packages=FakePackages())
    assert ctx.expand("socket", ":22")
    assert any(e.relation == "HELD_BY" and e.target == "process:42" for e in ctx.graph.edges)
    assert not ctx.graph.partial


def test_unresolved_owner(fs):
    put(fs, "/proc/net/udp", "header\n" + row(port="14E9", state="07"))
    ctx = Context(":5353", fs=fs, runner=FakeRunner(), packages=FakePackages())
    assert ctx.expand("socket", ":5353")
    assert ctx.graph.partial
