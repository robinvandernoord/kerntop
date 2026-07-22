"""Textual interface for the kerntop proof of concept."""

from __future__ import annotations

import asyncio
import os

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Static

from .apt_commands import PreviewAction, PreviewResult, run_preview
from .apt_compat import AptUnavailableError
from .apt_state import KernelState, load_kernel_state
from .kernels import KernelRecord


class TextScreen(ModalScreen[None]):
    """A scrollable modal used for help and apt preview output."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, title: str, content: str) -> None:
        super().__init__()
        self.title = title
        self.content = content

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Static(self.title, id="dialog-title")
            with VerticalScroll(id="dialog-content"):
                yield Static(self.content)
            yield Static("Esc or q closes this view.", id="dialog-help")

    def action_close(self) -> None:
        self.dismiss()


class KerntopApp(App[None]):
    """Read-only kernel discovery with simulation-only apt previews."""

    TITLE = "kerntop"
    CSS = """
    #mode { padding: 0 1; background: $surface; }
    #mode.root { color: $success; }
    #mode.read-only { color: $warning; }
    #summary { padding: 0 1; }
    DataTable { height: 1fr; }
    #dialog {
        width: 90%;
        height: 85%;
        padding: 1 2;
        border: heavy $accent;
        background: $surface;
    }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-content { height: 1fr; }
    #dialog-help { margin-top: 1; color: $text-muted; }
    """
    BINDINGS = [
        Binding("ctrl+c", "interrupt_quit", show=False, priority=True, system=True),
        ("q", "quit", "Quit"),
        ("h", "show_help", "Help"),
        ("r", "reload", "Reload cache"),
        ("i", "preview_install", "Preview install"),
        ("x", "preview_remove", "Preview removal"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.records: tuple[KernelRecord, ...] = ()
        self.interrupt_pending = False

    @property
    def is_root(self) -> bool:
        return os.geteuid() == 0

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(id="mode")
        yield Static(id="summary")
        yield DataTable(cursor_type="row")
        yield Footer()

    def on_mount(self) -> None:
        mode = self.query_one("#mode", Static)
        if self.is_root:
            mode.update("Root mode: apt-get simulations are available; no changes are made.")
            mode.add_class("root")
        else:
            mode.update("Read-only mode: run kerntop with sudo to enable apt-get previews.")
            mode.add_class("read-only")
        self.action_reload()

    def action_reload(self) -> None:
        self.run_worker(self.load_state(), group="load-state", exclusive=True)

    def action_interrupt_quit(self) -> None:
        """Require a second Ctrl-C to terminate the application immediately."""
        if self.interrupt_pending:
            self.exit()
        else:
            self.interrupt_pending = True
            self.notify(
                "Press Ctrl-C again to quit immediately.",
                title="Do you want to quit?",
                severity="warning",
            )

    async def load_state(self) -> None:
        summary = self.query_one("#summary", Static)
        summary.update("Loading the local apt cache…")
        try:
            state = await asyncio.to_thread(load_kernel_state)
        except AptUnavailableError as error:
            self.records = ()
            self.render_error(str(error))
            return
        except Exception as error:
            self.records = ()
            self.render_error(f"Unable to read the apt cache: {error}")
            return
        self.render_state(state)

    def render_error(self, message: str) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        self.query_one("#summary", Static).update(message)

    def render_state(self, state: KernelState) -> None:
        self.records = state.records
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("Kernel", "State", "Installed", "Candidate", "Headers")
        for record in self.records:
            status = "RUNNING" if record.running else "installed" if record.installed else "available"
            installed = record.installed_version or "—"
            candidate = record.candidate_version or "—"
            headers = ", ".join(header.name.removeprefix("linux-headers-") for header in record.headers)
            table.add_row(record.identifier, status, installed, candidate, headers or "—")
        self.query_one("#summary", Static).update(
            f"{len(self.records)} kernel image(s) for {state.native_architecture}; "
            f"running: {state.running_release}"
        )

    def selected_record(self) -> KernelRecord | None:
        cursor_row = self.query_one(DataTable).cursor_row
        if cursor_row < 0 or cursor_row >= len(self.records):
            return None
        return self.records[cursor_row]

    def action_preview_install(self) -> None:
        self.start_preview(PreviewAction.INSTALL)

    def action_preview_remove(self) -> None:
        self.start_preview(PreviewAction.REMOVE)

    def start_preview(self, action: PreviewAction) -> None:
        if not self.is_root:
            self.notify("Preview controls require launching the full program with sudo.", severity="warning")
            return
        record = self.selected_record()
        if record is None:
            self.notify("Select a kernel image first.", severity="warning")
            return
        self.run_worker(self.preview(action, record), group="preview", exclusive=True)

    async def preview(self, action: PreviewAction, record: KernelRecord) -> None:
        try:
            result = await asyncio.to_thread(run_preview, action, record)
        except ValueError as error:
            self.notify(str(error), severity="error")
            return
        self.show_preview(action, result)

    def show_preview(self, action: PreviewAction, result: PreviewResult) -> None:
        command = " ".join(result.command)
        content = f"$ {command}\n\n{result.output or '(no output)'}"
        title = f"{action.value.title()} preview (exit status {result.return_code})"
        self.push_screen(TextScreen(title, content))

    def action_show_help(self) -> None:
        self.push_screen(
            TextScreen(
                "kerntop 0.0.1 proof of concept",
                "Arrow keys: choose a kernel image\n"
                "i: simulate installation\n"
                "x: simulate removal (running kernel is blocked)\n"
                "r: reload the local apt cache\n"
                "q: quit\n\n"
                "This release never installs, removes, purges, or updates packages.",
            )
        )
