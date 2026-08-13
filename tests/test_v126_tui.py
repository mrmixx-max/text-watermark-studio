"""Tests for the menu-driven Textual TUI (2026-08-13).

Contract: 16 menu entries, every entry maps to a real action method, the app
composes its widgets, and the CLI subcommand exists. The app itself is not
run here (needs a terminal); textual's headless pilot covers that path in
CI via `ai-wm tui` smoke when a TTY is present.
"""

import pytest

textual = pytest.importorskip("textual", reason="textual not installed (tui extra)")

from ai_watermark_toolkit.ui.tui import MENU, SHORT_HELP, StudioTUI  # noqa: E402


class TestMenu:
    def test_menu_has_25_entries(self):
        assert len(MENU) == 25

    def test_every_entry_maps_to_action_method(self):
        app = StudioTUI()
        for label, action_id in MENU:
            method = "action_" + action_id.replace("-", "_")
            assert hasattr(app, method), f"missing {method} for menu entry {label!r}"

    def test_every_action_has_help(self):
        for _, action_id in MENU:
            assert action_id in SHORT_HELP, f"missing help for {action_id}"

    def test_labels_are_numbered_sequentially(self):
        numbers = [label.split()[0] for label, _ in MENU]
        assert numbers == [str(i) for i in range(1, 26)]


class TestCompose:
    def test_app_composes_widgets(self):
        import asyncio

        async def check():
            app = StudioTUI()
            async with app.run_test() as pilot:
                app.query_one("#menu-list")
                app.query_one("#out")
                app.query_one("#path")

        asyncio.run(check())

    def test_bindings_exist(self):
        app = StudioTUI()
        bound = {b.key for b in app.BINDINGS}
        assert "q" in bound  # quit must always be reachable
        assert "enter" in bound
        assert "up" in bound
        assert "down" in bound


class TestCursorNavigation:
    def test_arrows_move_menu_from_input_focus(self):
        import asyncio

        async def nav():
            app = StudioTUI()
            async with app.run_test(size=(120, 36)) as pilot:
                # focus sits on the Path input — arrows must still drive the menu
                app.query_one("#path").focus()
                await pilot.pause()
                lv = app.query_one("#menu-list")
                lv.index = 0
                await pilot.press("down")
                assert lv.index == 1
                await pilot.press("down")
                assert lv.index == 2
                await pilot.press("up")
                assert lv.index == 1
                # clamp at both ends
                lv.index = len(MENU) - 1
                await pilot.press("down")
                assert lv.index == len(MENU) - 1
                lv.index = 0
                await pilot.press("up")
                assert lv.index == 0

        asyncio.run(nav())
