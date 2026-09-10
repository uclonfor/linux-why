import subprocess

from linux_why.utils.command import Runner


def test_missing(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(runner, "which", lambda name: None)
    assert runner.run(["absent"]).code == 127


def test_timeout(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(runner, "which", lambda name: "/usr/bin/test")

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("test", 3)

    monkeypatch.setattr(subprocess, "run", timeout)
    assert runner.run(["test"]).code == 124


def test_no_shell_and_cache(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(runner, "which", lambda name: "/usr/bin/pacman")
    calls = []

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0, "ok", "")

    monkeypatch.setattr(subprocess, "run", run)
    args = ["pacman", "-Qqo", "--", "/tmp/$(touch evil); *"]
    assert runner.run(args).stdout == "ok"
    runner.run(args)
    assert len(calls) == 1
    assert calls[0][0][-1] == args[-1]
    assert not calls[0][1].get("shell", False)
    assert calls[0][1]["env"]["LC_ALL"] == "C"
    assert calls[0][1]["timeout"] == 3


def test_budget():
    assert Runner(budget=0).run(["anything"]).code == 125


def test_spawn_permission_denied(monkeypatch):
    runner = Runner()
    monkeypatch.setattr(runner, "which", lambda name: "/usr/bin/tool")

    def denied(*args, **kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(subprocess, "run", denied)
    assert runner.run(["tool"]).code == 126


def test_total_time_budget(monkeypatch):
    runner = Runner()
    runner.deadline = 0
    assert runner.run(["tool"]).problem == "External command time budget reached"
