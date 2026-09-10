import argparse
import json
import os
import sys
from collections.abc import Sequence

from linux_why import __version__
from linux_why.core.graph import Context
from linux_why.core.models import Candidate
from linux_why.core.renderer import render, safe
from linux_why.core.resolver import resolve


def choose_candidate(candidates: Sequence[Candidate]) -> str | None:
    from linux_why.tui.chooser import choose

    return choose(candidates)


def interactive_terminal() -> bool:
    return (
        sys.stdin.isatty()
        and sys.stdout.isatty()
        and os.environ.get("TERM", "").lower() not in {"", "dumb", "unknown"}
    )


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(
        prog="linux-why",
        description='Ask your Linux system "why is this here?"',
        epilog=(
            "Prefixes: package:, file:, pid:, process:, service:, unit:, "
            "tcp:, udp:, interface:, module:"
        ),
    )
    result.add_argument("target", nargs="?", help="object to explain; omit to browse interactively")
    result.add_argument("--version", action="version", version=f"linux-why {__version__}")
    result.add_argument("--json", action="store_true", help="emit the versioned graph schema")
    result.add_argument(
        "--verbose", "-v", action="store_true", help="show evidence sources and confidence"
    )
    result.add_argument("--no-color", action="store_true", help="disable ANSI colors")
    result.add_argument(
        "--depth", type=int, default=5, help="maximum expansion depth, 0–10 (default: 5)"
    )
    result.add_argument(
        "--debug", action="store_true", help="show tracebacks for unexpected errors"
    )
    return result


def main(argv: Sequence[str] | None = None) -> int:
    arguments = list(argv if argv is not None else sys.argv[1:])
    if arguments[:1] == ["explain"]:
        arguments.pop(0)
    cli = parser()
    options = cli.parse_args(arguments)
    if not 0 <= options.depth <= 10:
        cli.error("--depth must be between 0 and 10")
    if options.target is None:
        if options.json or list(argv if argv is not None else sys.argv[1:])[:1] == ["explain"]:
            cli.error("TARGET is required for --json or explain")
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            print(
                "Interactive mode requires a TTY.\n\nUsage:\n"
                "  linux-why TARGET\n  linux-why --help",
                file=sys.stderr,
            )
            return 2
        if os.environ.get("TERM", "").lower() in {"", "dumb", "unknown"}:
            print(
                "Interactive mode requires a cursor-addressable terminal (TERM is unset/dumb)."
                "\nUse linux-why TARGET or linux-why --help.",
                file=sys.stderr,
            )
            return 2
        from linux_why.tui.app import WhyApp

        try:
            WhyApp(depth=options.depth, verbose=options.verbose).run()
        except (OSError, RuntimeError) as exc:
            if options.debug:
                raise
            print("linux-why: interactive mode unavailable: " + safe(str(exc)), file=sys.stderr)
            return 3
        return 0
    ctx = Context(options.target, options.depth)
    try:
        code = resolve(ctx)
        if ctx.graph.candidates and not options.json and interactive_terminal():
            selected = choose_candidate(ctx.graph.candidates)
            if selected is None:
                return 0
            # Fresh query budget and evidence: do not reuse the ambiguity graph.
            ctx = Context(selected, options.depth)
            code = resolve(ctx)
    except KeyboardInterrupt:
        return 130
    except ValueError as exc:
        cli.error(str(exc))
    except (OSError, RuntimeError) as exc:
        if options.debug:
            raise
        ctx.warning(f"System data unavailable: {exc}")
        code = 3
    except Exception as exc:
        if options.debug:
            raise
        print(
            f"linux-why: unexpected internal error ({type(exc).__name__}); retry with --debug",
            file=sys.stderr,
        )
        return 3
    try:
        if options.json:
            print(json.dumps(ctx.graph.to_dict(), indent=2, ensure_ascii=True))
        else:
            print(
                render(
                    ctx.graph,
                    verbose=options.verbose,
                    color=sys.stdout.isatty()
                    and not options.no_color
                    and "NO_COLOR" not in os.environ,
                )
            )
        if options.json:
            for warning in ctx.graph.warnings:
                print("linux-why: " + safe(warning), file=sys.stderr)
    except BrokenPipeError:
        # Prevent a second BrokenPipeError during interpreter shutdown.
        with open(os.devnull, "w") as sink:
            os.dup2(sink.fileno(), sys.stdout.fileno())
    return code
