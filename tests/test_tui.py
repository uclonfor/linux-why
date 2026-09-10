import pytest
from conftest import FakePackages, FakeRunner, pkg
from textual.widgets import OptionList, RichLog

from linux_why.core.graph import Context
from linux_why.core.inventory import CATEGORIES, Catalog, Entry, Inventory
from linux_why.core.resolver import resolve
from linux_why.tui.app import ExplanationReady, WhyApp
from linux_why.tui.logo import full_logo, render_logo


class FixtureCatalog(Catalog):
    def __init__(self):
        super().__init__()
        self.calls = []
        self.cache = {kind: Inventory() for kind in [*CATEGORIES, "file"]}
        self.cache["package"] = Inventory(
            [
                Entry("package", "acl", "package:acl", "1.0 dependency"),
                Entry("package", "firefox", "package:firefox", "143 explicit"),
                Entry("package", "firewalld", "package:firewalld", "2 dependency"),
                Entry("package", "qemu", "package:qemu", "10 explicit"),
            ]
        )
        self.cache["module"] = Inventory([Entry("module", "firewire", "module:firewire")])

    def load(self, category):
        self.calls.append(category)
        return super().load(category)


@pytest.fixture
def app(fs):
    targets = []
    packages = FakePackages({name: pkg(name) for name in ["acl", "firefox", "firewalld", "qemu"]})

    def explain(target, depth):
        targets.append(target)
        ctx = Context(target, depth, fs=fs, runner=FakeRunner(), packages=packages)
        resolve(ctx)
        return ctx.graph

    application = WhyApp(catalog=FixtureCatalog(), resolver=explain)
    application.resolved_targets = targets
    return application


async def settled(app, pilot):
    await app.workers.wait_for_complete()
    await pilot.pause()


async def test_initial_selection_and_enter_opens_packages(app):
    async with app.run_test() as pilot:
        options = app.query_one(OptionList)
        assert options.highlighted == 0
        assert app.visible_entries[0].name == "Installed packages"
        assert app.focused is options
        assert app.catalog.calls == []
        assert [entry.target for entry in app.visible_entries] == list(CATEGORIES)
        await pilot.press("enter")
        await settled(app, pilot)
        assert app.view.mode == "browser"
        assert app.view.category == "package"
        assert len(app.visible_entries) == 4
        assert not app.stopping.is_set()
        await pilot.press("ctrl+q")
    assert app.return_code == 0


async def test_down_enter_opens_services(app):
    async with app.run_test() as pilot:
        await pilot.press("down")
        assert app.query_one(OptionList).highlighted == 1
        await pilot.press("enter")
        await settled(app, pilot)
        assert app.view.mode == "browser"
        assert app.view.category == "unit"
        assert app.focused is app.query_one(OptionList)
        assert not app.visible_entries


async def test_first_letter_and_query(app):
    async with app.run_test() as pilot:
        await pilot.press("f")
        assert app.view.query == "f"
        await pilot.press("i", "r", "e")
        await settled(app, pilot)
        assert app.view.query == "fire"
        assert any(entry.name == "firefox" for entry in app.visible_entries)
        assert any(entry.category == "module" for entry in app.visible_entries)
        assert all(app.catalog.calls.count(kind) == 1 for kind in [*CATEGORIES, "file"])
        await pilot.press("backspace", "e")
        await settled(app, pilot)
        assert app.view.query == "fire"
        assert len(app.catalog.calls) == 7


async def test_search_arrows_and_existing_resolver(app):
    async with app.run_test() as pilot:
        await pilot.press(*"fire")
        await settled(app, pilot)
        options = app.query_one(OptionList)
        options.highlighted = 0
        await pilot.press("down")
        assert options.highlighted == 1
        target = app.visible_entries[1].target
        await pilot.press("enter")
        await settled(app, pilot)
        assert app.view.mode == "result"
        assert app.resolved_targets == [target]
        assert app.view.graph.roots == [target]
        assert app.focused is app.query_one(RichLog)
        await pilot.press("escape")
        assert app.view.mode == "home"
        assert app.view.query == "fire"
        assert app.focused is options


async def test_escape_clears_query_to_main_menu(app):
    async with app.run_test() as pilot:
        await pilot.press(*"fire")
        await settled(app, pilot)
        await pilot.press("escape")
        assert app.view.query == ""
        assert app.query_one(OptionList).highlighted == 0
        assert app.visible_entries[0].name == "Installed packages"
        await pilot.press("escape")
        assert not app.stopping.is_set()


async def test_q_is_search_ctrl_q_is_exit(app):
    async with app.run_test() as pilot:
        await pilot.press("q")
        assert app.view.query == "q"
        assert not app.stopping.is_set()
        await pilot.press("e", "m", "u")
        assert app.view.query == "qemu"
        await pilot.press("ctrl+q")
        assert app.stopping.is_set()


async def test_browser_type_filter_and_back(app):
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settled(app, pilot)
        await pilot.press("f")
        assert app.view.query == "f"
        await pilot.press("i", "r", "e")
        assert app.view.query == "fire"
        assert [entry.name for entry in app.visible_entries] == ["firefox", "firewalld"]
        await pilot.press("enter")
        await settled(app, pilot)
        assert app.view.mode == "result"
        assert app.resolved_targets == ["package:firefox"]
        await pilot.press("escape")
        assert app.view.mode == "browser"
        assert app.view.query == "fire"
        await pilot.press("down")
        assert app.query_one(OptionList).highlighted == 1
        await pilot.press("escape")
        assert app.view.query == ""
        assert app.view.mode == "browser"
        await pilot.press("backspace")
        assert app.view.mode == "browser"
        await pilot.press("escape")
        assert app.view.mode == "home"


async def test_unicode_and_printable_symbols(app):
    async with app.run_test() as pilot:
        await pilot.press(*"тест")
        assert app.view.query == "тест"
        await pilot.press("escape")
        await pilot.press(*"aZ0_-.:/@")
        assert app.view.query == "aZ0_-.:/@"
        await pilot.press("backspace")
        assert app.view.query == "aZ0_-.:/"


@pytest.mark.parametrize("size", [(80, 24), (140, 45), (35, 18), (20, 12)])
async def test_terminal_sizes(app, size):
    async with app.run_test(size=size) as pilot:
        assert app.visible_entries[0].name == "Installed packages"
        await pilot.press("enter")
        await settled(app, pilot)
        await pilot.press(*"fire")
        assert app.view.query == "fire"
        await pilot.press("ctrl+q")


def test_figlet_logo_and_fallback():
    banner = full_logo()
    assert "\n" in banner
    width = max(map(len, banner.splitlines()))
    assert render_logo(width) == banner
    assert render_logo(width - 1) == "linux-why"
    assert render_logo(20) == "linux-why"
    assert render_logo(140, 12) == "linux-why"


async def test_empty_results_and_selection_clamping(app):
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settled(app, pilot)
        await pilot.press("end")
        assert app.query_one(OptionList).highlighted == 3
        await pilot.press(*"zzzz")
        assert app.visible_entries == []
        assert app.query_one(OptionList).highlighted is None
        await pilot.press("down", "up", "enter", "home", "end", "pageup", "pagedown")
        assert app.view.mode == "browser"
        await pilot.press("escape", "end")
        assert app.query_one(OptionList).highlighted == 3


async def test_late_result_does_not_replace_returned_view(app):
    async with app.run_test() as pilot:
        generation = app.generation
        graph = app.resolver("package:firefox", 1)
        await pilot.press("enter")
        app.post_message(ExplanationReady(generation - 1, graph))
        await pilot.pause()
        assert app.view.mode == "browser"


async def test_paste_once(app):
    from textual.events import Paste

    async with app.run_test() as pilot:
        app.post_message(Paste("тест\nfire"))
        await pilot.pause()
        assert app.view.query == "тестfire"


async def test_verbose_toggle_reuses_graph(app):
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settled(app, pilot)
        await pilot.press("enter")
        await settled(app, pilot)
        graph = app.view.graph
        await pilot.press("f2")
        assert app.verbose
        assert app.view.graph is graph
        assert len(app.resolved_targets) == 1
        await pilot.press("ctrl+q")
        assert app.stopping.is_set()


async def test_stale_option_event_cannot_open_different_object(app):
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settled(app, pilot)
        options = app.query_one(OptionList)
        old_event = OptionList.OptionSelected(options, options.get_option_at_index(0), 0)
        await pilot.press(*"fire")
        app.post_message(old_event)
        await pilot.pause()
        assert app.view.mode == "browser"
        assert not app.resolved_targets


async def test_empty_backspace_preserves_selection(app):
    async with app.run_test() as pilot:
        await pilot.press("enter")
        await settled(app, pilot)
        await pilot.press("end")
        selected = app.query_one(OptionList).highlighted
        await pilot.press("backspace")
        assert app.view.query == ""
        assert app.query_one(OptionList).highlighted == selected
