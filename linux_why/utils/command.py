"""The only subprocess entry point; no shell, stdin, privilege escalation or writes."""

import os
import shutil
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class Result:
    code: int
    stdout: str = ""
    stderr: str = ""
    problem: str | None = None


class Runner:
    def __init__(self, timeout: float = 3.0, budget: int = 100) -> None:
        self.cancelled: Callable[[], bool] = lambda: False
        self.deadline = time.monotonic() + 15.0
        self.timeout = timeout
        self.budget = budget
        self.cache: dict[tuple[str, ...], Result] = {}

    def which(self, name: str) -> str | None:
        return shutil.which(name)

    def run(self, args: list[str]) -> Result:
        if self.cancelled():
            return Result(125, problem="Query cancelled")
        key = tuple(args)
        if key in self.cache:
            return self.cache[key]
        remaining = self.deadline - time.monotonic()
        if remaining <= 0:
            return Result(124, problem="External command time budget reached")
        if self.budget <= 0:
            return Result(125, problem="External command budget reached")
        self.budget -= 1
        binary = self.which(args[0])
        if not binary:
            result = Result(127, problem=f"Optional command unavailable: {args[0]}")
        else:
            env = {
                **os.environ,
                "LC_ALL": "C",
                "LANG": "C",
                "SYSTEMD_PAGER": "cat",
                "SYSTEMD_COLORS": "0",
                "SYSTEMD_ASK_PASSWORD": "0",
            }
            try:
                completed = subprocess.run(
                    [binary, *args[1:]],
                    stdin=subprocess.DEVNULL,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    timeout=min(self.timeout, remaining),
                    env=env,
                    check=False,
                )
                result = Result(completed.returncode, completed.stdout, completed.stderr)
            except subprocess.TimeoutExpired:
                result = Result(124, problem=f"Command timed out: {args[0]}")
            except OSError as exc:
                result = Result(126, problem=f"Cannot run {args[0]}: {exc.strerror}")
        self.cache[key] = result
        return result
