from conftest import FakePackages, FakeRunner, pkg, put

from linux_why.backends.packages.pacman import Pacman, fields
from linux_why.core.graph import Context
from linux_why.utils.command import Result
from linux_why.utils.platform import package_backend

INFO = """Name            : libxcrypt-compat
Version         : 4.4.38-1
Required By     : spotify
                  another-app
Install Date    : Wed 09 Sep 2026 10:00:00 AM UTC
Install Reason  : Installed as a dependency for another package
"""


def test_pacman(fs):
    runner = FakeRunner({("pacman", "-Qi", "--", "libxcrypt-compat"): Result(0, INFO)})
    put(
        fs,
        "/var/log/pacman.log",
        "[2026-09-01T10:00:00+0000] [ALPM] installed libxcrypt-compat (4.4.38-1)\n",
    )
    backend = Pacman(runner, fs)
    package = backend.get("libxcrypt-compat")
    assert package.reason == "dependency"
    assert package.required_by == ["spotify", "another-app"]
    assert package.log_event.startswith("2026-09-01")
    assert backend.get("libxcrypt-compat") is package
    assert len(runner.calls) == 1


def test_fields_with_colon():
    assert (
        fields("URL             : https://example.org:8080\n")["URL"] == "https://example.org:8080"
    )


def test_reverse_tree_and_cycle(fs):
    backend = FakePackages({"a": pkg("a", ["b"]), "b": pkg("b", ["a"], "explicit")})
    ctx = Context("a", packages=backend, fs=fs, runner=FakeRunner())
    ctx.expand("package", "a")
    assert len(ctx.graph.nodes) == 2
    assert len(ctx.graph.edges) == 2
    assert {e.relation for e in ctx.graph.edges} == {"REQUIRED_BY"}
    assert ctx.graph.nodes["package:b"].attributes["install_reason"].value == "explicit"


def test_depth(fs):
    ctx = Context(
        "a",
        0,
        fs=fs,
        runner=FakeRunner(),
        packages=FakePackages({"a": pkg("a", ["b"]), "b": pkg("b")}),
    )
    ctx.expand("package", "a")
    assert list(ctx.graph.nodes) == ["package:a"]
    assert not ctx.graph.partial
    assert ctx.graph.warnings


def test_missing_pacman(fs):
    ctx = Context("a", fs=fs, runner=FakeRunner())
    assert ctx.expand("package", "a") is None
    assert ctx.graph.partial


def test_unsupported(fs):
    put(fs, "/etc/os-release", "ID=alpine\n")
    backend = package_backend(fs, FakeRunner())
    assert backend.get("anything") is None
    assert "alpine" in backend.problem


def test_derivative(fs):
    put(fs, "/etc/os-release", 'ID=endeavouros\nID_LIKE="arch"\n')
    assert isinstance(package_backend(fs, FakeRunner()), Pacman)


def test_missing_reason_is_partial(fs):
    runner = FakeRunner({("pacman", "-Qi", "--", "a"): Result(0, "Name : a\nVersion : 1\n")})
    ctx = Context("a", fs=fs, runner=runner)
    ctx.expand("package", "a")
    assert ctx.graph.partial


def test_expac_optional(fs):
    runner = FakeRunner(
        {
            ("pacman", "-Qi", "--", "libxcrypt-compat"): Result(0, INFO),
            ("expac", "%n\t%v", "--", "libxcrypt-compat"): Result(0, "libxcrypt-compat\tother\n"),
        },
        {"expac": "/usr/bin/expac"},
    )
    assert Pacman(runner, fs).get("libxcrypt-compat").warnings


def test_pacman_ownership_and_unowned(fs):
    runner = FakeRunner(
        {
            ("pacman", "-Qqo", "--", "/usr/bin/tool"): Result(0, "tool\n"),
            ("pacman", "-Qqo", "--", "/tmp/unowned"): Result(
                1, stderr="error: No package owns /tmp/unowned"
            ),
        }
    )
    backend = Pacman(runner, fs)
    assert backend.owner("/usr/bin/tool") == ["tool"]
    assert backend.owner("/tmp/unowned") == []
    assert backend.problem is None


def test_pacman_not_installed(fs):
    runner = FakeRunner(
        {
            ("pacman", "-Qi", "--", "missing"): Result(
                1, stderr="error: package 'missing' was not found"
            )
        }
    )
    backend = Pacman(runner, fs)
    assert backend.get("missing") is None
    assert backend.problem is None


def test_cached_package_clears_previous_error(fs):
    runner = FakeRunner({("pacman", "-Qi", "--", "libxcrypt-compat"): Result(0, INFO)})
    backend = Pacman(runner, fs)
    assert backend.get("libxcrypt-compat")
    backend.owner("/missing")
    assert backend.problem
    assert backend.get("libxcrypt-compat")
    assert backend.problem is None


def test_dpkg_architecture_ownership(fs):
    from linux_why.backends.packages.dpkg import Dpkg

    runner = FakeRunner(
        {
            ("dpkg-query", "-S", "--", "/usr/lib/libc.so"): Result(
                0, "libc6:amd64: /usr/lib/libc.so\n"
            )
        }
    )
    assert Dpkg(runner).owner("/usr/lib/libc.so") == ["libc6:amd64"]
