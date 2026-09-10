"""Compact ambiguity selection; return a typed target before CLI rendering resumes."""

from collections.abc import Sequence

from rich.text import Text
from textual import events
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from linux_why.core.models import Candidate
from linux_why.core.renderer import safe


class InterpretationChooser(App[str | None]):
    TITLE = "linux-why"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("escape", "cancel", "Cancel", priority=True),
        Binding("ctrl+c", "cancel", "Cancel", priority=True),
        Binding("ctrl+q", "cancel", "Cancel", priority=True),
    ]
    CSS = """
    Screen { background: $background; color: $foreground; padding: 1; }
    #heading { height: auto; margin-bottom: 1; text-style: bold; }
    #choices { height: 1fr; min-height: 1; border: none; padding: 0; }
    #choices:focus { border: none; }
    #keys { height: auto; color: $text-muted; }
    """

    def __init__(self, candidates: Sequence[Candidate]) -> None:
        super().__init__(ansi_color=True)
        self.theme = "textual-ansi"
        self.candidates = tuple(candidates)
        self.labels = []
        for candidate in self.candidates:
            kind = candidate.type
            if kind == "file" and candidate.label.startswith("executable:"):
                kind = "executable"
            self.labels.append(safe(f"{kind:<12} {candidate.value}"))
        self.marked: int | None = None

    def compose(self) -> ComposeResult:
        yield Static("Multiple interpretations found:", id="heading", markup=False)
        yield OptionList(
            *(Option(Text("  " + label), id=str(index)) for index, label in enumerate(self.labels)),
            id="choices",
            markup=False,
            compact=True,
        )
        yield Static(
            "↑↓ Select  Enter Explain  1–9 Quick select  Esc / Ctrl+C Cancel",
            id="keys",
            markup=False,
        )

    def on_mount(self) -> None:
        if not self.candidates:
            self.exit(None)
            return
        options = self.query_one(OptionList)
        options.highlighted = 0
        options.focus()
        self.mark(0)

    def mark(self, index: int) -> None:
        options = self.query_one(OptionList)
        for position in (self.marked, index):
            if position is not None and 0 <= position < len(self.labels):
                options.replace_option_prompt_at_index(
                    position, Text(("> " if position == index else "  ") + self.labels[position])
                )
        self.marked = index

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        self.mark(event.option_index)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        self.select(event.option_index)

    def select(self, index: int) -> None:
        if 0 <= index < len(self.candidates):
            self.exit(self.candidates[index].explicit_target)

    def on_key(self, event: events.Key) -> None:
        if event.character and event.character in "123456789":
            event.stop()
            event.prevent_default()
            self.select(int(event.character) - 1)

    def action_cancel(self) -> None:
        self.exit(None)


def choose(candidates: Sequence[Candidate]) -> str | None:
    try:
        return InterpretationChooser(candidates).run()
    except KeyboardInterrupt:
        return None
