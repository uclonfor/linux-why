import pytest
from conftest import FakePackages, FakeRunner, make_process, pkg

from linux_why.core.detector import detect, port_query


@pytest.mark.parametrize(
    ("target", "kind", "value"),
    [
        ("package:glibc", "package", "glibc"),
        ("/usr/bin/bash", "file", "/usr/bin/bash"),
        ("pid:0012", "process", "12"),
        ("1337", "process", "1337"),
        ("service:sshd", "unit", "sshd.service"),
        ("sshd.service", "unit", "sshd.service"),
        (":22", "socket", ":22"),
        ("tcp:8080", "socket", "tcp:8080"),
        ("udp:5353", "socket", "udp:5353"),
        ("interface:lo", "interface", "lo"),
        ("module:nvidia-drm", "module", "nvidia_drm"),
    ],
)
def test_explicit(fs, target, kind, value):
    assert [(c.type, c.value) for c in detect(target, fs, FakeRunner(), FakePackages())] == [
        (kind, value)
    ]


@pytest.mark.parametrize(
    "target",
    [
        "pid:0",
        "pid:-1",
        "pid:abc",
        "tcp:65536",
        ":-1",
        "file:relative",
        "package:*",
        "module:../../etc/passwd",
        "unit:--all",
        "interface:../lo",
        "x\n",
    ],
)
def test_invalid(fs, target):
    with pytest.raises(ValueError):
        detect(target, fs, FakeRunner(), FakePackages())


def test_ambiguity(fs):
    make_process(fs, 21, "ssh")
    candidates = detect(
        "ssh", fs, FakeRunner(binaries={"ssh": "/usr/bin/ssh"}), FakePackages({"ssh": pkg("ssh")})
    )
    assert {c.type for c in candidates} == {"file", "package", "process"}


def test_process_name(fs):
    make_process(fs, 21, "sshd")
    assert detect("process:sshd", fs, FakeRunner(), FakePackages())[0].value == "21"


@pytest.mark.parametrize(
    ("value", "address", "port", "proto"),
    [
        ("0.0.0.0:8000", "0.0.0.0", 8000, None),
        ("[::1]:22", "::1", 22, None),
        ("udp:5353", None, 5353, "udp"),
        (":0", None, 0, None),
    ],
)
def test_ports(value, address, port, proto):
    result = port_query(value)
    assert (result.address, result.port, result.protocol) == (address, port, proto)


def test_unknown(fs):
    assert detect("no-such-object", fs, FakeRunner(), FakePackages()) == []


def test_permission_does_not_hide_package(fs, monkeypatch):
    original = fs.list

    def listing(path):
        if path == "/sys/class/net":
            raise PermissionError(path)
        return original(path)

    monkeypatch.setattr(fs, "list", listing)
    warnings = []
    candidates = detect(
        "test", fs, FakeRunner(), FakePackages({"test": pkg("test")}), warnings.append
    )
    assert any(candidate.type == "package" for candidate in candidates)
    assert warnings


def test_empty_service_prefix(fs):
    with pytest.raises(ValueError):
        detect("service:", fs, FakeRunner(), FakePackages())
