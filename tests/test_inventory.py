import json

from conftest import FakePackages, FakeRunner, make_process, put

from linux_why.backends.packages.dpkg import Dpkg
from linux_why.backends.packages.pacman import Pacman
from linux_why.backends.systemd import list_services
from linux_why.core.graph import Context
from linux_why.core.inventory import Catalog, collect
from linux_why.utils.command import Result


def test_pacman_inventory_uses_two_bulk_queries(fs):
    runner = FakeRunner(
        {
            ("pacman", "-Q"): Result(0, "acl 2.3\nfirefox 143\n"),
            ("pacman", "-Qqe"): Result(0, "firefox\n"),
        }
    )
    backend = Pacman(runner, fs)
    catalog = Catalog(lambda: Context("inventory", fs=fs, runner=runner, packages=backend))
    first = catalog.load("package")
    assert [entry.detail for entry in first.entries] == ["2.3  dependency", "143  explicit"]
    assert catalog.load("package") is first
    assert runner.calls == [["pacman", "-Q"], ["pacman", "-Qqe"]]


def test_pacman_unknown_reason_when_query_fails(fs):
    runner = FakeRunner({("pacman", "-Q"): Result(0, "acl 2.3\n")})
    backend = Pacman(runner, fs)
    assert backend.list_installed()[0].reason == "unknown"
    assert backend.problem


def test_dpkg_inventory_filters_removed_packages(fs):
    runner = FakeRunner(
        {
            ("dpkg-query", "-W", "-f=${binary:Package}\t${Version}\t${db:Status-Status}\n"): Result(
                0, "bash\t5.3\tinstalled\nold\t1.0\tconfig-files\n"
            )
        }
    )
    packages = Dpkg(runner).list_installed()
    assert [pkg.name for pkg in packages] == ["bash"]
    assert packages[0].reason == "unknown"


def test_systemd_join():
    prefix = (
        "systemctl",
        "--no-pager",
        "--no-ask-password",
        "--output=json",
        "--type=service",
        "--all",
    )
    runner = FakeRunner(
        {
            (*prefix, "list-unit-files"): Result(
                0, json.dumps([{"unit_file": "sshd.service", "state": "enabled"}])
            ),
            (*prefix, "list-units"): Result(
                0, json.dumps([{"unit": "sshd.service", "active": "active"}])
            ),
        }
    )
    records, warnings = list_services(runner)
    assert records == [("sshd.service", "active", "enabled")]
    assert not warnings


def test_malformed_service_inventory():
    prefix = (
        "systemctl",
        "--no-pager",
        "--no-ask-password",
        "--output=json",
        "--type=service",
        "--all",
    )
    runner = FakeRunner({(*prefix, "list-unit-files"): Result(0, "oops")})
    assert list_services(runner)[1]


def test_process_module_and_interface_inventory(fs):
    make_process(fs, 42, "firefox")
    fs.path("/sys/class/net/lo").mkdir(parents=True)
    fs.path("/sys/module/loop").mkdir(parents=True)
    put(fs, "/proc/modules", "loop 123 0 - Live 0x00\n")
    ctx = Context("inventory", fs=fs, runner=FakeRunner(), packages=FakePackages())
    assert collect(ctx, "process")[0].target == "pid:42"
    assert collect(ctx, "interface")[0].target == "interface:lo"
    assert collect(ctx, "module")[0].target == "module:loop"


def test_unsupported_inventory_is_partial(fs):
    put(fs, "/etc/os-release", "ID=alpine\n")
    catalog = Catalog(lambda: Context("inventory", fs=fs, runner=FakeRunner()))
    inventory = catalog.load("package")
    assert not inventory.entries
    assert "alpine" in inventory.warnings[0]


def test_failed_service_state_inventory_is_unknown():
    prefix = (
        "systemctl",
        "--no-pager",
        "--no-ask-password",
        "--output=json",
        "--type=service",
        "--all",
    )
    runner = FakeRunner(
        {
            (*prefix, "list-unit-files"): Result(
                0, '[{"unit_file":"sshd.service","state":"enabled"}]'
            )
        }
    )
    services, warnings = list_services(runner)
    assert services == [("sshd.service", "unknown", "enabled")]
    assert warnings
