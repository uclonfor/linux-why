"""Exercise Textual's real terminal lifecycle, including return to plain output."""

import os
import select
import subprocess
import sys
import time

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="Linux PTY integration")
@pytest.mark.parametrize(
    "keys,expected", [(b"\x1b", "None"), (b"\x03", "None"), (b"\x1b[B\r", "file:/usr/bin/firefox")]
)
def test_terminal_restored(keys, expected):
    import fcntl
    import pty
    import struct
    import termios

    try:
        master, slave = pty.openpty()
    except OSError as exc:
        pytest.skip(f"PTY unavailable: {exc}")
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    before = termios.tcgetattr(slave)
    script = """
from linux_why.core.models import Candidate
from linux_why.tui.chooser import choose
value = choose([Candidate("package", "firefox", "package: firefox"),
                Candidate("file", "/usr/bin/firefox", "executable: /usr/bin/firefox")])
print("SELECTED=" + str(value), flush=True)
"""
    process = subprocess.Popen(
        [sys.executable, "-c", script],
        stdin=slave,
        stdout=slave,
        stderr=slave,
        env={**os.environ, "TERM": "xterm"},
    )
    data = bytearray()
    sent = False
    try:
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if select.select([master], [], [], 0.05)[0]:
                data.extend(os.read(master, 65536))
            if not sent and b"Quick select" in data:
                assert process.poll() is None
                os.write(master, keys)
                sent = True
            if process.poll() is not None:
                while select.select([master], [], [], 0.05)[0]:
                    data.extend(os.read(master, 65536))
                break
        assert sent
        assert process.poll() == 0, data.decode(errors="replace")
        assert ("SELECTED=" + expected).encode() in data
        assert b"Traceback" not in data
        assert b"\x1b[?1049l" in data and b"\x1b[?25h" in data
        assert termios.tcgetattr(slave) == before
    finally:
        if process.poll() is None:
            process.kill()
            process.wait()
        os.close(master)
        os.close(slave)
