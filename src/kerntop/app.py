"""Textual interface for the kerntop proof of concept."""

import asyncio
import os
import typing as t

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    LoadingIndicator,
    OptionList,
    Static,
)

from .apt_commands import PreviewAction, PreviewResult, run_preview
from .apt_compat import AptUnavailableError
from .apt_state import KernelState, load_kernel_state
from .kernels import (
    KernelRecord,
    KernelSeries,
    PackageState,
    kernel_records,
    kernel_series,
)


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
        with Container(id="text-dialog"):
            yield Static(self.title, id="dialog-title")
            with VerticalScroll(id="dialog-content"):
                yield Static(self.content)
            yield Static("Esc or q closes this view.", id="dialog-help")

    def action_close(self) -> None:
        self.dismiss()


class KernelActionsScreen(ModalScreen[PreviewAction | None]):
    """A context-aware action prompt for one kernel image."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(self, record: KernelRecord, can_preview: bool) -> None:
        super().__init__()
        self.record = record
        self.can_preview = can_preview
        if can_preview and not record.installed:
            self.actions = (PreviewAction.INSTALL,)
        elif can_preview and record.installed and not record.running:
            self.actions = (PreviewAction.REMOVE,)
        else:
            self.actions = ()

    def compose(self) -> ComposeResult:
        status = (
            "currently running"
            if self.record.running
            else "installed"
            if self.record.installed
            else "available"
        )
        details = f"{self.record.identifier}\n\nState: {status}"
        if not self.can_preview:
            details += "\n\nRun kerntop with sudo to preview package actions."
        elif self.record.running:
            details += "\n\nThe running kernel cannot be removed."
        with Container(id="action-dialog"):
            yield Static("Kernel actions", id="dialog-title")
            yield Static(details)
            if self.actions:
                yield OptionList(
                    *(f"Preview {action.value}" for action in self.actions),
                    id="kernel-actions",
                )
                yield Static(
                    "Arrow keys choose an action; Enter confirms.",
                    id="dialog-help",
                )
            else:
                yield Static("Esc or q closes this view.", id="dialog-help")

    def on_mount(self) -> None:
        """Give the selectable action list keyboard focus immediately."""
        if self.actions:
            self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Return the action chosen with Enter from the option list."""
        if event.option_list.id == "kernel-actions":
            self.dismiss(self.actions[event.option_index])

    def action_close(self) -> None:
        self.dismiss()


class PreviewProgressScreen(ModalScreen[None]):
    """Show that an apt simulation is running before its output is available."""

    def __init__(self, action: PreviewAction, record: KernelRecord) -> None:
        super().__init__()
        self.action = action
        self.record = record

    def compose(self) -> ComposeResult:
        with Container(id="progress-dialog"):
            yield Static(
                f"Simulating {self.action.value}: {self.record.identifier}",
                id="dialog-title",
            )
            yield LoadingIndicator()
            yield Static("Waiting for apt-get…", id="dialog-help")


class KerntopApp(App[None]):
    """Read-only kernel discovery with simulation-only apt previews."""

    TITLE = "kerntop"
    CSS = """
    #mode { padding: 0 1; background: $surface; }
    #mode.root { color: $success; }
    #mode.read-only { color: $warning; }
    #summary { padding: 0 1; }
    DataTable { height: 1fr; }
    DataTable > .datatable--cursor { text-style: none; }
    DataTable:focus > .datatable--cursor { text-style: none; }
    ModalScreen { align: center middle; }
    #text-dialog {
        width: 60%;
        height: 85%;
        padding: 1 2;
        border: heavy $accent;
        background: $surface;
    }
    #action-dialog {
        width: 60%;
        height: auto;
        padding: 1 2;
        border: heavy $accent;
        background: $surface;
    }
    #progress-dialog {
        width: 60%;
        height: 8;
        padding: 1 2;
        border: heavy $accent;
        background: $surface;
    }
    #kernel-actions { border: none; padding: 0; }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-content { height: 1fr; }
    #dialog-help { margin-top: 1; color: $text-muted; }
    """
    BINDINGS = [
        Binding("ctrl+c", "interrupt_quit", show=False, priority=True, system=True),
        ("h", "show_help", "Help"),
        ("r", "reload", "Reload cache"),
        ("a", "toggle_all_variants", "Toggle variants"),
        ("escape", "back_to_series", "Back / quit"),
        Binding("left", "return_to_series", show=False),
        ("i", "preview_install", "Preview install"),
        ("x", "preview_remove", "Preview removal"),
    ]

    def __init__(self) -> None:
        super().__init__()
        self.records: tuple[KernelRecord, ...] = ()
        self.packages: tuple[PackageState, ...] = ()
        self.series: tuple[KernelSeries, ...] = ()
        self.active_series: KernelSeries | None = None
        self.native_architecture = ""
        self.running_release = ""
        self.escape_pending = False
        self.show_all_variants = False

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
            mode.update(
                "Root mode: apt-get simulations are available; no changes are made."
            )
            mode.add_class("root")
        else:
            mode.update(
                "Read-only mode: run kerntop with sudo to enable apt-get previews."
            )
            mode.add_class("read-only")
        self.action_reload()

    def action_reload(self) -> None:
        self.run_worker(self.load_state(), group="load-state", exclusive=True)

    def action_interrupt_quit(self) -> None:
        """Exit immediately when the terminal sends an interrupt."""
        self.exit()

    async def load_state(self) -> None:
        summary = self.query_one("#summary", Static)
        summary.update("Loading the local apt cache…")
        try:
            state = await asyncio.to_thread(
                load_kernel_state,
                include_all_variants=self.show_all_variants,
            )
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
        self.packages = state.packages
        self.active_series = None
        self.native_architecture = state.native_architecture
        self.running_release = state.running_release
        self.refresh_records()
        self.render_series()

    def refresh_records(self) -> None:
        """Rebuild the displayed records from the cached kernel package state."""
        self.records = kernel_records(
            self.packages,
            self.native_architecture,
            self.running_release,
            include_all_variants=self.show_all_variants,
        )
        self.series = kernel_series(self.records)

    def render_series(self) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_columns("Kernel series", "Installed", "Available", "Builds")
        for series in self.series:
            table.add_row(
                series.name,
                str(series.installed_count),
                str(series.available_count),
                str(len(series.records)),
            )
        self.query_one("#summary", Static).update(
            f"{len(self.series)} kernel series for {self.native_architecture}; "
            f"running: {self.running_release}. "
            f"Showing {'all variants' if self.show_all_variants else 'recommended variants'}. "
            "Press Enter to view builds."
        )
        self.refresh_bindings()

    def render_builds(self, series: KernelSeries) -> None:
        table = self.query_one(DataTable)
        table.clear(columns=True)
        table.add_column("Build / flavour", width=24)
        table.add_column("State", width=10)
        table.add_column("Installed", width=17)
        table.add_column("Candidate", width=17)
        table.add_column("Headers", width=24)
        for record in series.records:
            status = (
                "RUNNING"
                if record.running
                else "installed"
                if record.installed
                else "available"
            )
            installed = record.installed_version or "—"
            candidate = record.candidate_version or "—"
            headers = ", ".join(
                header.name.removeprefix("linux-headers-") for header in record.headers
            )
            table.add_row(
                record.identifier, status, installed, candidate, headers or "—"
            )
        self.query_one("#summary", Static).update(
            f"Kernel series {series.name}: {len(series.records)} build(s); "
            f"showing {'all variants' if self.show_all_variants else 'recommended variants'}. "
            "Press Enter for actions."
        )
        self.refresh_bindings()

    def check_action(self, action: str, _parameters: tuple[t.Any, ...]) -> bool | None:
        """Expose navigation and package actions only in their relevant view."""
        if action in {"preview_install", "preview_remove"}:
            return self.active_series is not None
        return True

    def on_data_table_row_selected(self, _event: DataTable.RowSelected) -> None:
        """Open a selected series or show actions for a selected build."""
        if self.active_series is None:
            self.action_open_series()
        else:
            record = self.selected_record()
            if record is not None:
                self.show_kernel_actions(record)

    def action_open_series(self) -> None:
        if self.active_series is not None:
            return
        cursor_row = self.query_one(DataTable).cursor_row
        if cursor_row < 0 or cursor_row >= len(self.series):
            self.notify("Select a kernel series first.", severity="warning")
            return
        self.active_series = self.series[cursor_row]
        self.render_builds(self.active_series)

    def action_toggle_all_variants(self) -> None:
        """Switch views without reopening the local apt cache."""
        active_series_name = self.active_series.name if self.active_series else None
        self.show_all_variants = not self.show_all_variants
        self.escape_pending = False
        self.refresh_records()
        self.active_series = next(
            (series for series in self.series if series.name == active_series_name),
            None,
        )
        if self.active_series is None:
            self.render_series()
        else:
            self.render_builds(self.active_series)

    def show_kernel_actions(self, record: KernelRecord) -> None:
        """Open the context-aware action prompt for a kernel build."""
        self.push_screen(
            KernelActionsScreen(record, self.is_root),
            self.handle_kernel_action,
        )

    def handle_kernel_action(self, action: PreviewAction | None) -> None:
        """Run a requested preview after the action prompt closes."""
        if action is not None:
            self.start_preview(action)

    def action_back_to_series(self) -> None:
        if self.active_series is not None:
            self.action_return_to_series()
            return
        if self.escape_pending:
            self.exit()
            return
        self.escape_pending = True
        self.notify(
            "Press Esc again to quit.",
            title="Do you want to quit?",
            severity="warning",
        )

    def action_return_to_series(self) -> None:
        """Return from a build list without treating Left as an exit key."""
        if self.active_series is None:
            return
        self.active_series = None
        self.escape_pending = False
        self.render_series()

    def selected_record(self) -> KernelRecord | None:
        if self.active_series is None:
            return None
        cursor_row = self.query_one(DataTable).cursor_row
        if cursor_row < 0 or cursor_row >= len(self.active_series.records):
            return None
        return self.active_series.records[cursor_row]

    def action_preview_install(self) -> None:
        self.start_preview(PreviewAction.INSTALL)

    def action_preview_remove(self) -> None:
        self.start_preview(PreviewAction.REMOVE)

    def start_preview(self, action: PreviewAction) -> None:
        if not self.is_root:
            self.notify(
                "Preview controls require launching the full program with sudo.",
                severity="warning",
            )
            return
        record = self.selected_record()
        if record is None:
            self.notify(
                "Open a kernel series and select a build first.", severity="warning"
            )
            return
        self.push_screen(PreviewProgressScreen(action, record))
        self.run_worker(self.preview(action, record), group="preview", exclusive=True)

    async def preview(self, action: PreviewAction, record: KernelRecord) -> None:
        try:
            result = await asyncio.to_thread(run_preview, action, record)
        except ValueError as error:
            self.close_preview_progress()
            self.notify(str(error), severity="error")
            return
        self.show_preview(action, result)

    def close_preview_progress(self) -> None:
        """Dismiss the temporary progress modal before showing a result."""
        if isinstance(self.screen, PreviewProgressScreen):
            self.pop_screen()

    def show_preview(self, action: PreviewAction, result: PreviewResult) -> None:
        self.close_preview_progress()
        command = " ".join(result.command)
        content = f"$ {command}\n\n{result.output or '(no output)'}"
        title = f"{action.value.title()} preview (exit status {result.return_code})"
        self.push_screen(TextScreen(title, content))

    def action_show_help(self) -> None:
        self.push_screen(
            TextScreen(
                "kerntop 0.1.0 minimum viable manager",
                "Arrow keys: choose a row\n"
                "Enter: open the selected item\n"
                "Esc or Left: return to the series list; press Esc twice there to quit\n"
                "a: toggle recommended and all kernel variants\n"
                "i: simulate installation\n"
                "x: simulate removal (running kernel is blocked)\n"
                "r: reload the local apt cache\n\n"
                "This release never installs, removes, purges, or updates packages.",
            )
        )
