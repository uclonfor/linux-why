"""Keyboard-first Textual presentation over the existing resolver and renderer."""

from collections.abc import Callable
from dataclasses import dataclass, field
from threading import Event

from rich.text import Text
from textual import events, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.message import Message
from textual.widgets import OptionList, RichLog, Static
from textual.widgets.option_list import Option
from textual.worker import get_current_worker

from linux_why.core.graph import Context
from linux_why.core.inventory import CATEGORIES, Catalog, Entry, Inventory
from linux_why.core.models import Graph
from linux_why.core.renderer import render, safe
from linux_why.core.resolver import resolve
from linux_why.tui.logo import TAGLINE, render_logo


@dataclass
class View:
    mode: str = "home"
    category: str = ""
    query: str = ""
    selected: int = 0
    target: str = ""
    graph: Graph | None = None
    choices: list[Entry] = field(default_factory=list)


class InventoryReady(Message):
    def __init__(self, category: str, inventory: Inventory) -> None:
        super().__init__()
        self.category, self.inventory = category, inventory


class ExplanationReady(Message):
    def __init__(self, generation: int, graph: Graph) -> None:
        super().__init__()
        self.generation, self.graph = generation, graph


class WhyApp(App[None]):
    TITLE = "linux-why"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        Binding("ctrl+q", "exit_app", "Quit", priority=True),
        Binding("escape", "go_back", "Back / clear", priority=True),
        Binding("f2", "verbose", "Evidence", priority=True),
    ]
    CSS = """
    Screen { background: $background; color: $foreground; padding: 0 1; }
    #logo { width: 100%; height: auto; content-align: center middle;
            text-wrap: nowrap; text-overflow: clip; color: $accent; }
    #tagline { height: 1; text-align: center; margin-bottom: 1; }
    #heading { height: 1; text-style: bold; }
    #query { height: 1; margin-bottom: 1; }
    #items { height: 1fr; min-height: 2; border: none; padding: 0; }
    #items:focus { border: none; }
    #explanation { height: 1fr; min-height: 2; border: none; padding: 0; }
    #status { height: auto; max-height: 3; color: $text-muted; }
    #keys { height: auto; color: $text-muted; }
    """

    def __init__(
        self,
        *,
        catalog: Catalog | None = None,
        resolver: Callable[[str, int], Graph] | None = None,
        depth: int = 5,
        verbose: bool = False,
    ) -> None:
        # ANSI palette works over SSH and on terminals without truecolor.
        super().__init__(ansi_color=True)
        self.theme = "textual-ansi"
        self.stopping = Event()
        self.catalog = catalog or Catalog(self.new_context)
        self.resolver = resolver or self.explain
        self.depth, self.verbose = depth, verbose
        self.view = View()
        self.history: list[View] = []
        self.loaded: dict[str, Inventory] = {}
        self.requested: set[str] = set()
        self.visible_entries: list[Entry] = []
        self.option_labels: list[str] = []
        self.marked_index: int | None = None
        self.option_epoch = 0
        self.generation = 0
        self.ready = False

    def new_context(self) -> Context:
        ctx = Context("inventory", getattr(self, "depth", 5))
        ctx.runner.cancelled = self.stopping.is_set
        return ctx

    def explain(self, target: str, depth: int) -> Graph:
        ctx = self.new_context()
        ctx.graph.target = target
        resolve(ctx)
        return ctx.graph

    def compose(self) -> ComposeResult:
        yield Static("", id="logo", markup=False)
        yield Static(TAGLINE, id="tagline", markup=False)
        yield Static("", id="heading", markup=False)
        yield Static("Search: ", id="query", markup=False)
        yield OptionList(id="items", markup=False, compact=True)
        yield RichLog(id="explanation", markup=False, highlight=False, wrap=False)
        yield Static("", id="status", markup=False)
        yield Static("", id="keys", markup=False)

    def on_mount(self) -> None:
        self.ready = True
        self.resize_logo()
        self.show_view()

    def on_resize(self, event: events.Resize) -> None:
        if self.ready:
            self.resize_logo()

    def resize_logo(self) -> None:
        self.query_one("#logo", Static).update(
            render_logo(max(0, self.size.width - 2), self.size.height)
        )

    def show_view(self) -> None:
        is_result = self.view.mode == "result"
        self.query_one("#items", OptionList).display = not is_result
        self.query_one("#explanation", RichLog).display = is_result
        self.query_one("#query", Static).display = not is_result
        self.query_one("#logo", Static).display = self.view.mode == "home"
        self.query_one("#tagline", Static).display = self.view.mode == "home"
        if is_result:
            self.query_one("#heading", Static).update("linux-why › " + safe(self.view.target))
            log = self.query_one("#explanation", RichLog)
            log.clear()
            log.write(
                Text(render(self.view.graph, verbose=self.verbose))
                if self.view.graph
                else Text("Resolving local evidence…")
            )
            log.scroll_home(animate=False)
            log.focus()
            self.query_one("#status", Static).update(
                "Partial result — see warnings above."
                if self.view.graph and self.view.graph.partial
                else ""
            )
            self.query_one("#keys", Static).update("↑↓ Scroll  Esc Back  F2 Evidence  Ctrl+Q Quit")
        else:
            self.refresh_choices()
            self.query_one("#items", OptionList).focus()
            self.query_one("#keys", Static).update(
                "↑↓ Navigate  Enter Open  Type to search  Esc Clear / back  Ctrl+Q Quit"
            )

    def request(self, categories: list[str]) -> None:
        missing = [category for category in categories if category not in self.requested]
        self.requested.update(missing)
        if missing:
            self.load_inventories(missing)

    @work(thread=True, exit_on_error=False)
    def load_inventories(self, categories: list[str]) -> None:
        for category in categories:
            if self.stopping.is_set() or get_current_worker().is_cancelled:
                return
            try:
                inventory = self.catalog.load(category)
            except Exception as exc:
                inventory = Inventory(
                    warnings=[f"Inventory unavailable: {type(exc).__name__}: {exc}"]
                )
            if not self.stopping.is_set():
                self.post_message(InventoryReady(category, inventory))

    def on_inventory_ready(self, message: InventoryReady) -> None:
        self.loaded[message.category] = message.inventory
        if self.view.mode in {"home", "browser"}:
            self.refresh_choices(preserve=True)

    def refresh_choices(self, *, preserve: bool = False) -> None:
        options = self.query_one("#items", OptionList)
        old = options.highlighted
        previous = (
            self.visible_entries[old].target
            if old is not None and old < len(self.visible_entries)
            else None
        )
        if len(self.visible_entries) == 1 and self.visible_entries[0].category == "query":
            previous = None
        query = self.view.query.casefold()
        warnings: list[str] = []
        pending = False
        if self.view.mode == "home" and not query:
            self.visible_entries = [
                Entry("menu", title, kind) for kind, title in CATEGORIES.items()
            ]
            heading = "Browse your Linux system"
        else:
            if self.view.mode == "home":
                categories = [*CATEGORIES, "file"]
                heading = "Search results"
            elif self.view.mode == "choices":
                categories = []
                heading = "Multiple interpretations — choose an object"
            else:
                categories = [self.view.category]
                heading = CATEGORIES[self.view.category]
            entries = list(self.view.choices)
            for category in categories:
                inventory = self.loaded.get(category)
                if inventory is None:
                    pending = True
                    continue
                entries.extend(inventory.entries)
                warnings.extend(inventory.warnings)
            self.visible_entries = [
                entry for entry in entries if query in (entry.name + " " + entry.detail).casefold()
            ]
            heading += f" · {len(self.visible_entries)} objects"
            if self.view.mode == "home":
                # Neutral action, not a guessed type. Exact queries go through detect().
                self.visible_entries.append(
                    Entry("query", f"Explain exact target: {self.view.query}", self.view.query)
                )
        self.query_one("#heading", Static).update(heading)
        self.query_one("#query", Static).update("Search: " + safe(self.view.query))
        labels = []
        self.option_labels = []
        self.marked_index = None
        self.option_epoch += 1
        for index, entry in enumerate(self.visible_entries):
            prefix = (
                f"{entry.category}  "
                if self.view.mode == "home" and query and entry.category != "query"
                else ""
            )
            label = prefix + entry.name + ("  " + entry.detail if entry.detail else "")
            self.option_labels.append(safe(label))
            labels.append(Option(Text("  " + safe(label)), id=f"{self.option_epoch}:{index}"))
        options.clear_options().add_options(labels)
        index = self.view.selected
        if preserve and previous is not None:
            index = next(
                (i for i, entry in enumerate(self.visible_entries) if entry.target == previous),
                index,
            )
        options.highlighted = (
            min(index, len(self.visible_entries) - 1) if self.visible_entries else None
        )
        self.view.selected = options.highlighted or 0
        self.mark_selection(options.highlighted)
        messages = ["Loading local inventory…"] if pending else []
        if not self.visible_entries:
            messages.append("No matching objects.")
        messages.extend(dict.fromkeys(safe(warning) for warning in warnings))
        self.query_one("#status", Static).update("\n".join(messages))

    def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_id != f"{self.option_epoch}:{event.option_index}":
            return
        self.view.selected = event.option_index
        self.mark_selection(event.option_index)

    def mark_selection(self, index: int | None) -> None:
        options = self.query_one("#items", OptionList)
        for position in (self.marked_index, index):
            if position is not None and 0 <= position < len(self.option_labels):
                marker = "> " if position == index else "  "
                options.replace_option_prompt_at_index(
                    position, Text(marker + self.option_labels[position])
                )
        self.marked_index = index

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if (
            event.option_id != f"{self.option_epoch}:{event.option_index}"
            or event.option_index >= len(self.visible_entries)
        ):
            return
        if self.view.mode == "result":
            return
        entry = self.visible_entries[event.option_index]
        self.view.selected = event.option_index
        if entry.category == "menu":
            self.history.append(self.view)
            self.view = View(mode="browser", category=entry.target)
            self.request([entry.target])
            self.show_view()
        else:
            self.open_target(entry.target)

    def open_target(self, target: str) -> None:
        self.history.append(self.view)
        self.view = View(mode="result", target=target)
        self.generation += 1
        self.show_view()
        self.resolve_target(target, self.generation)

    @work(thread=True, group="explanation", exclusive=True, exit_on_error=False)
    def resolve_target(self, target: str, generation: int) -> None:
        try:
            graph = self.resolver(target, self.depth)
        except Exception as exc:
            graph = Graph(target)
            graph.warn(f"Unable to resolve target: {type(exc).__name__}: {exc}")
        if not self.stopping.is_set() and not get_current_worker().is_cancelled:
            self.post_message(ExplanationReady(generation, graph))

    def on_explanation_ready(self, message: ExplanationReady) -> None:
        if message.generation != self.generation or self.view.mode != "result":
            return
        graph = message.graph
        self.view.graph = graph
        if graph.candidates:
            self.view.mode = "choices"
            self.view.choices = [
                Entry(c.type, c.label, c.explicit_target) for c in graph.candidates
            ]
        self.show_view()

    def on_key(self, event: events.Key) -> None:
        if self.view.mode == "result":
            return
        if event.key == "backspace":
            event.stop()
            event.prevent_default()
            if self.view.query:
                self.change_query(self.view.query[:-1])
        elif event.character and event.character.isprintable():
            event.stop()
            event.prevent_default()
            self.change_query(self.view.query + event.character)

    def on_paste(self, event: events.Paste) -> None:
        if self.view.mode != "result":
            event.stop()
            self.change_query(self.view.query + "".join(c for c in event.text if c.isprintable()))

    def change_query(self, query: str) -> None:
        self.view.query = query[:512]
        self.view.selected = 0
        if self.view.mode == "home" and self.view.query:
            self.request([*CATEGORIES, "file"])
        self.refresh_choices()

    def action_go_back(self) -> None:
        if self.view.mode != "result" and self.view.query:
            self.change_query("")
            return
        if self.history:
            self.generation += 1
            self.view = self.history.pop()
            self.show_view()

    def action_verbose(self) -> None:
        if self.view.mode == "result":
            self.verbose = not self.verbose
            self.show_view()

    def action_exit_app(self) -> None:
        self.stopping.set()
        self.workers.cancel_all()
        self.exit()
