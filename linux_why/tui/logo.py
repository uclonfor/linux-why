"""A real FIGlet banner, with no wrapping or clipping at small terminal sizes."""

from functools import lru_cache

from pyfiglet import Figlet

FONT = "standard"
TAGLINE = 'Ask your Linux system "why?"'


@lru_cache(maxsize=1)
def full_logo() -> str:
    return "\n".join(
        line.rstrip()
        for line in str(Figlet(font=FONT, width=200).renderText("linux-why")).splitlines()
    ).rstrip()


def render_logo(width: int, height: int = 24) -> str:
    logo = full_logo()
    if width < max(map(len, logo.splitlines())) or height < 20:
        return "linux-why"
    return logo
