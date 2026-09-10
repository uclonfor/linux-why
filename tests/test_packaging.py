"""Entry-point contracts and opt-in clean wheel installation (also run in CI)."""

import importlib.metadata
import os
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

from linux_why import cli

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]["scripts"]


@pytest.mark.parametrize("name", ["linux-why", "why"])
def test_entry_point(name):
    entry = importlib.metadata.EntryPoint(name=name, value=SCRIPTS[name], group="console_scripts")
    assert entry.load() is cli.main
    assert SCRIPTS[name] == SCRIPTS["linux-why"]


@pytest.mark.parametrize("option", ["--help", "--version"])
def test_short_entry_information(option, capsys):
    entry = importlib.metadata.EntryPoint(
        name="why", value=SCRIPTS["why"], group="console_scripts"
    ).load()
    with pytest.raises(SystemExit) as result:
        entry([option])
    assert result.value.code == 0
    assert "linux-why" in capsys.readouterr().out


def test_clean_wheel_install(tmp_path):
    wheel_name = os.environ.get("LINUX_WHY_TEST_WHEEL")
    if not wheel_name:
        pytest.skip("Set LINUX_WHY_TEST_WHEEL to exercise clean wheel installation")
    wheel = Path(wheel_name).resolve(strict=True)
    venv = tmp_path / "installed"
    env = {k: v for k, v in os.environ.items() if k not in {"PYTHONPATH", "PYTHONHOME"}}

    def run(args, timeout=120):
        return subprocess.run(
            args, cwd=tmp_path, env=env, capture_output=True, text=True, timeout=timeout
        )

    result = run([sys.executable, "-m", "venv", str(venv)])
    assert result.returncode == 0, result.stderr
    python = str(venv / "bin/python")
    result = run([python, "-m", "pip", "install", "--disable-pip-version-check", str(wheel)], 240)
    assert result.returncode == 0, result.stderr
    env["PATH"] = str(venv / "bin") + os.pathsep + env.get("PATH", "")
    for name in ("linux-why", "why"):
        result = run(["sh", "-c", f"command -v {name}"])
        assert result.returncode == 0 and result.stdout.strip() == str(venv / "bin" / name)
        for flag in ("--help", "--version"):
            result = run([name, flag])
            assert result.returncode == 0 and "linux-why" in result.stdout
    # Imports must come from the wheel, not the checkout or an editable install.
    result = run([python, "-c", "import linux_why; print(linux_why.__file__)"])
    assert str(venv) in result.stdout
    for target in ("firefox", "package:firefox", "/usr/bin/bash", "lo"):
        result = run(["why", target, "--depth", "0"])
        original = run(["linux-why", target, "--depth", "0"])
        assert result.returncode in (0, 1, 2, 3)
        # Live observations can differ between runs (process races / command timeouts).
        # Callable identity and deterministic resolver behavior are checked separately.
        assert original.returncode in (0, 1, 2, 3)
        assert target.removeprefix("package:") in result.stdout
        assert target.removeprefix("package:") in original.stdout
        assert "Traceback" not in result.stderr + original.stderr
    result = run(["why"])
    assert result.returncode == 2 and "requires a TTY" in result.stderr
    # Keep the path visible for debugging installation failures in CI.
    assert (venv / "bin/why").is_file()


def test_short_entry_resolver_and_chooser(fs, monkeypatch, capsys):
    from conftest import FakePackages, FakeRunner, pkg, put

    from linux_why.core.graph import Context

    put(fs, "/usr/bin/firefox", "fixture")
    targets = []

    def context(target, depth):
        targets.append(target)
        return Context(
            target,
            depth,
            fs=fs,
            runner=FakeRunner(binaries={"firefox": "/usr/bin/firefox"}),
            packages=FakePackages({"firefox": pkg("firefox")}),
        )

    monkeypatch.setattr(cli, "Context", context)
    monkeypatch.setattr(cli, "interactive_terminal", lambda: True)
    choices = []

    def choose(candidates):
        choices.extend(c.explicit_target for c in candidates)
        return candidates[1].explicit_target

    monkeypatch.setattr(cli, "choose_candidate", choose)
    entry = importlib.metadata.EntryPoint(
        name="why", value=SCRIPTS["why"], group="console_scripts"
    ).load()
    assert entry(["firefox", "--depth", "0"]) == 0
    assert choices == ["package:firefox", "file:/usr/bin/firefox"]
    assert targets == ["firefox", "file:/usr/bin/firefox"]
    assert "/usr/bin/firefox" in capsys.readouterr().out


def test_short_entry_starts_existing_tui(monkeypatch):
    from linux_why.tui.app import WhyApp

    launched = []
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm")
    monkeypatch.setattr(WhyApp, "run", lambda self: launched.append(type(self)))
    entry = importlib.metadata.EntryPoint(
        name="why", value=SCRIPTS["why"], group="console_scripts"
    ).load()
    assert entry([]) == 0
    assert launched == [WhyApp]
