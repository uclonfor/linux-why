import json
from importlib.resources import files

import jsonschema
import pytest
from conftest import FakePackages, FakeRunner, pkg

from linux_why import cli
from linux_why.core.graph import Context
from linux_why.core.models import Claim, Confidence, Graph
from linux_why.core.renderer import render


def test_json_schema(fs, monkeypatch, capsys):
    ctx = Context("a", fs=fs, runner=FakeRunner(), packages=FakePackages({"a": pkg("a")}))
    monkeypatch.setattr(cli, "Context", lambda *args: ctx)
    assert cli.main(["package:a", "--json"]) == 0
    output = capsys.readouterr()
    data = json.loads(output.out)
    schema = json.loads(files("linux_why").joinpath("schema.json").read_text())
    jsonschema.validate(data, schema)
    assert not output.err


def test_renderer_cycles_and_controls():
    graph = Graph("x")
    a = graph.node("file", "x", "unsafe\x1b[2J")
    b = graph.node("file", "y")
    a.attributes["creator"] = Claim("maybe", "heuristic", Confidence.INFERRED)
    graph.roots.append(a.id)
    graph.link(a, b, "OWNS", "test")
    graph.link(b, a, "OWNED_BY", "test")
    text = render(graph, verbose=True)
    assert "already shown" in text
    assert "\x1b" not in text
    assert "inferred; heuristic" in text


@pytest.mark.parametrize("argv", [["--help"], ["--version"]])
def test_information(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        cli.main(argv)
    assert exc.value.code == 0
    assert "linux-why" in capsys.readouterr().out


def test_not_found(fs, monkeypatch, capsys):
    ctx = Context("missing", fs=fs, runner=FakeRunner(), packages=FakePackages())
    monkeypatch.setattr(cli, "Context", lambda *args: ctx)
    assert cli.main(["package:missing"]) == 1
    assert "Could not determine" in capsys.readouterr().out


def test_partial_json(fs, monkeypatch, capsys):
    ctx = Context("a", fs=fs, runner=FakeRunner())
    monkeypatch.setattr(cli, "Context", lambda *args: ctx)
    assert cli.main(["package:a", "--json"]) == 3
    output = capsys.readouterr()
    assert json.loads(output.out)["partial"]
    assert "pacman" in output.err


def test_ambiguity(fs, monkeypatch, capsys):
    ctx = Context(
        "a",
        fs=fs,
        runner=FakeRunner(binaries={"a": "/usr/bin/a"}),
        packages=FakePackages({"a": pkg("a")}),
    )
    monkeypatch.setattr(cli, "Context", lambda *args: ctx)
    assert cli.main(["a"]) == 2
    assert "Multiple interpretations" in capsys.readouterr().out


def test_invalid_depth():
    with pytest.raises(SystemExit) as exc:
        cli.main(["x", "--depth", "-1"])
    assert exc.value.code == 2


def test_non_tty_interactive_fallback(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    assert cli.main([]) == 2
    output = capsys.readouterr()
    assert "Interactive mode requires a TTY." in output.err
    assert not output.out


@pytest.mark.parametrize("args", [["--json"], ["explain"]])
def test_missing_target_in_noninteractive_modes(args):
    with pytest.raises(SystemExit) as exc:
        cli.main(args)
    assert exc.value.code == 2


def test_dumb_terminal(monkeypatch, capsys):
    import sys

    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sys.stdout, "isatty", lambda: True)
    monkeypatch.setenv("TERM", "dumb")
    assert cli.main([]) == 2
    assert "cursor-addressable" in capsys.readouterr().err
