import json
import sys

import pytest
from conftest import FakePackages, FakeRunner, pkg, put
from textual.widgets import OptionList

from linux_why import cli
from linux_why.core.graph import Context
from linux_why.core.models import Candidate
from linux_why.tui.chooser import InterpretationChooser

CANDIDATES = [
    Candidate("package", "firefox", "package: firefox"),
    Candidate("file", "/usr/bin/firefox", "executable: /usr/bin/firefox"),
]


async def test_initial_and_arrows():
    app = InterpretationChooser(CANDIDATES)
    async with app.run_test() as pilot:
        choices = app.query_one(OptionList)
        assert choices.has_focus
        assert choices.highlighted == 0
        await pilot.press("down")
        assert choices.highlighted == 1
        await pilot.press("up")
        assert choices.highlighted == 0
        await pilot.press("down", "enter")
    assert app.return_value == "file:/usr/bin/firefox"


@pytest.mark.parametrize(
    "key,target",
    [
        ("enter", "package:firefox"),
        ("2", "file:/usr/bin/firefox"),
        ("escape", None),
        ("ctrl+c", None),
        ("ctrl+q", None),
    ],
)
async def test_select_and_cancel(key, target):
    app = InterpretationChooser(CANDIDATES)
    async with app.run_test() as pilot:
        await pilot.press(key)
        assert not app.is_running
    assert app.return_value == target


async def test_long_list_resize_and_invalid_number():
    app = InterpretationChooser([Candidate("process", str(i), "display") for i in range(50)])
    async with app.run_test(size=(80, 24)) as pilot:
        await pilot.press("end")
        await pilot.resize_terminal(24, 12)
        await pilot.pause()
        choices = app.query_one(OptionList)
        assert choices.highlighted == 49
        assert choices.scroll_y > 0
        await pilot.press("enter")
    assert app.return_value == "pid:49"
    app = InterpretationChooser(CANDIDATES)
    async with app.run_test(size=(24, 12)) as pilot:
        await pilot.press("9")
        assert app.is_running
        await pilot.press("escape")


@pytest.mark.parametrize(
    "kind,value,expected",
    [
        ("package", "firefox", "package:firefox"),
        ("file", "/bin/a:b", "file:/bin/a:b"),
        ("process", "123", "pid:123"),
        ("socket", "tcp:22", "tcp:22"),
        ("unit", "a.service", "unit:a.service"),
    ],
)
def test_explicit_target_independent_of_label(kind, value, expected):
    assert Candidate(kind, value, "misleading display").explicit_target == expected


@pytest.fixture
def contexts(fs, monkeypatch, capsys):
    put(fs, "/usr/bin/firefox", "fixture")
    seen = []

    def context(target, depth):
        seen.append((target, depth))
        return Context(
            target,
            depth,
            fs=fs,
            runner=FakeRunner(binaries={"firefox": "/usr/bin/firefox"}),
            packages=FakePackages({"firefox": pkg("firefox")}),
        )

    monkeypatch.setattr(cli, "Context", context)
    return seen


def test_cli_selected_explicit_pipeline(contexts, monkeypatch, capsys):
    tty(monkeypatch)
    selected = []

    def choose(candidates):
        selected.extend(c.explicit_target for c in candidates)
        return candidates[1].explicit_target

    monkeypatch.setattr(cli, "choose_candidate", choose)
    assert cli.main(["firefox", "--depth", "0", "--no-color"]) == 0
    assert selected == ["package:firefox", "file:/usr/bin/firefox"]
    assert contexts == [("firefox", 0), ("file:/usr/bin/firefox", 0)]
    assert "/usr/bin/firefox" in capsys.readouterr().out


def test_cli_cancel(contexts, monkeypatch, capsys):
    tty(monkeypatch)
    monkeypatch.setattr(cli, "choose_candidate", lambda _: None)
    assert cli.main(["firefox"]) == 0
    assert len(contexts) == 1
    assert not capsys.readouterr().out


@pytest.mark.parametrize("mode", ["json", "stdin", "stdout", "dumb", "explicit"])
def test_no_chooser(contexts, monkeypatch, capsys, mode):
    tty(monkeypatch)

    def forbidden(_):
        pytest.fail("Non-interactive or explicit query opened chooser")

    monkeypatch.setattr(cli, "choose_candidate", forbidden)
    args = ["firefox", "--depth", "0"]
    if mode == "json":
        args.append("--json")
    elif mode in {"stdin", "stdout"}:
        monkeypatch.setattr(getattr(sys, mode), "isatty", lambda: False)
    elif mode == "dumb":
        monkeypatch.setenv("TERM", "dumb")
    else:
        args[0] = "package:firefox"
    assert cli.main(args) == (0 if mode == "explicit" else 2)
    output = capsys.readouterr().out
    if mode == "json":
        data = json.loads(output)
        assert data["detected_type"] == "ambiguous"
        assert [c["type"] for c in data["candidates"]] == ["package", "file"]
        assert "\x1b" not in output


def tty(monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "xterm")
