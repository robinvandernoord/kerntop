"""Textual interface for the kerntop proof of concept."""

import asyncio
import os
import typing as t
from dataclasses import dataclass

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import DataTable, Footer, Header, Log, OptionList, Static

from .apt_commands import PreviewAction, apply_command, preview_command
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


@dataclass(frozen=True)
class KernelAction:
    """An action available for the currently selected kernel image."""

    label: str
    action: PreviewAction
    applies_changes: bool


class KernelActionsScreen(ModalScreen[KernelAction | None]):
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
            self.actions = (
                KernelAction("Preview installation", PreviewAction.INSTALL, False),
                KernelAction("Install", PreviewAction.INSTALL, True),
            )
        elif can_preview and record.installed and not record.running:
            self.actions = (
                KernelAction("Preview removal", PreviewAction.REMOVE, False),
                KernelAction("Remove", PreviewAction.REMOVE, True),
            )
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
            details += "\n\nRun kerntop with sudo to enable package actions."
        elif self.record.running:
            details += "\n\nThe running kernel cannot be removed."
        with Container(id="action-dialog"):
            yield Static("Kernel actions", id="dialog-title")
            yield Static(details)
            if self.actions:
                yield OptionList(
                    *(action.label for action in self.actions),
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


class ApplyConfirmationScreen(ModalScreen[bool]):
    """Require an explicit choice before changing installed packages."""

    BINDINGS = [
        ("escape", "cancel", "Cancel"),
        ("q", "cancel", "Cancel"),
    ]

    def __init__(self, action: PreviewAction, record: KernelRecord) -> None:
        super().__init__()
        self.action = action
        self.record = record

    def compose(self) -> ComposeResult:
        with Container(id="action-dialog"):
            yield Static(f"Confirm {self.action.value}", id="dialog-title")
            yield Static(
                f"{self.record.identifier}\n\n"
                "This will change packages on this host using apt-get."
            )
            yield OptionList(
                "Cancel",
                f"Apply {self.action.value}",
                id="apply-confirmation",
            )
            yield Static(
                "Arrow keys choose an action; Enter confirms.",
                id="dialog-help",
            )

    def on_mount(self) -> None:
        """Put the safe Cancel choice under the cursor first."""
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Return whether the user selected the mutating action."""
        if event.option_list.id == "apply-confirmation":
            self.dismiss(event.option_index == 1)

    def action_cancel(self) -> None:
        self.dismiss(False)


class PreviewOutputScreen(ModalScreen[None]):
    """Show output from an apt simulation while it runs."""

    BINDINGS = [
        ("escape", "close", "Close"),
        ("q", "close", "Close"),
    ]

    def __init__(
        self,
        action: PreviewAction,
        record: KernelRecord,
        operation: str = "Simulating",
    ) -> None:
        super().__init__()
        self.action = action
        self.record = record
        self.operation = operation

    def compose(self) -> ComposeResult:
        with Container(id="text-dialog"):
            yield Static(
                f"{self.operation} {self.action.value}: {self.record.identifier}",
                id="dialog-title",
            )
            yield Log(auto_scroll=True, id="apt-output")
            yield Static("Running apt-get…", id="apt-status")
            yield Static("Esc or q closes this view.", id="dialog-help")

    def write_output(self, line: str) -> None:
        """Append an apt output line to the visible log."""
        self.query_one("#apt-output", Log).write_line(line)

    def finish(self, return_code: int) -> None:
        """Show that the apt process has completed."""
        status = self.query_one("#apt-status", Static)
        status.update(f"apt-get finished with exit status {return_code}.")
        status.add_class("success" if return_code == 0 else "failure")

    def action_close(self) -> None:
        self.dismiss()


class KerntopApp(App[None]):
    """Kernel discovery with root-only apt previews and package actions."""

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
    #kernel-actions, #apply-confirmation { border: none; padding: 0; }
    #apt-output { height: 1fr; }
    #apt-status.success { color: $success; }
    #apt-status.failure { color: $error; }
    #dialog-title { text-style: bold; margin-bottom: 1; }
    #dialog-content { height: 1fr; }
    #dialog-help { margin-top: 1; color: $text-muted; }
    """
    BINDINGS = [
        Binding("ctrl+c", "interrupt_quit", show=False, priority=True, system=True),
        ("h", "show_help", "Help"),
        ("r", "reload", "Reload cache"),
        ("a", "toggle_all_variants", "Toggle variants"),
        Binding("p", "preview_install_selected", "Preview install"),
        Binding("p", "preview_remove_selected", "Preview removal", priority=True),
        ("i", "install_selected", "Install"),
        ("d", "remove_selected", "Remove"),
        ("escape", "back_to_series", "Back / quit"),
        Binding("left", "return_to_series", show=False),
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
                "Root mode: previews and immediate package actions are available."
            )
            mode.add_class("root")
        else:
            mode.update(
                "Read-only mode: run kerntop with sudo to enable package actions."
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
        record = self.selected_record()
        if action == "preview_install_selected":
            return self.is_root and record is not None and not record.installed
        elif action == "preview_remove_selected":
            return (
                self.is_root
                and record is not None
                and record.installed
                and not record.running
            )
        elif action == "install_selected":
            return self.is_root and record is not None and not record.installed
        elif action == "remove_selected":
            return (
                self.is_root
                and record is not None
                and record.installed
                and not record.running
            )
        return True

    def on_data_table_row_highlighted(self, _event: DataTable.RowHighlighted) -> None:
        """Update footer actions for the newly highlighted kernel image."""
        self.refresh_bindings()

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

    def handle_kernel_action(self, action: KernelAction | None) -> None:
        """Run the selected preview or immediate package action."""
        if action is not None:
            if action.applies_changes:
                self.show_apply_confirmation(action.action)
            else:
                self.start_preview(action.action)

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

    def action_preview_install_selected(self) -> None:
        """Preview installation of the highlighted available image."""
        self.start_preview(PreviewAction.INSTALL)

    def action_preview_remove_selected(self) -> None:
        """Preview removal of the highlighted installed image."""
        self.start_preview(PreviewAction.REMOVE)

    def action_install_selected(self) -> None:
        """Confirm installation of the highlighted available image."""
        self.show_apply_confirmation(PreviewAction.INSTALL)

    def action_remove_selected(self) -> None:
        """Confirm removal of the highlighted installed image."""
        self.show_apply_confirmation(PreviewAction.REMOVE)

    def start_preview(self, action: PreviewAction) -> None:
        if not self.is_root:
            self.notify(
                "Package previews require launching the full program with sudo.",
                severity="warning",
            )
            return
        record = self.selected_record()
        if record is None:
            self.notify(
                "Open a kernel series and select a build first.", severity="warning"
            )
            return
        screen = PreviewOutputScreen(action, record)
        self.push_screen(screen)
        self.run_worker(
            self.preview(action, record, screen), group="preview", exclusive=True
        )

    async def preview(
        self,
        action: PreviewAction,
        record: KernelRecord,
        screen: PreviewOutputScreen,
    ) -> None:
        """Run an apt preview and stream its combined output to its modal."""
        try:
            command = preview_command(action, record)
        except ValueError as error:
            screen.dismiss()
            self.notify(str(error), severity="error")
            return
        screen.write_output(f"$ {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        while line := await process.stdout.readline():
            screen.write_output(line.decode(errors="replace").rstrip("\n"))
        screen.finish(await process.wait())

    def start_apply(self, action: PreviewAction) -> None:
        """Run a single immediate install or removal from the action popup."""
        if not self.is_root:
            self.notify(
                "Package actions require launching the full program with sudo.",
                severity="warning",
            )
            return
        record = self.selected_record()
        if record is None:
            self.notify(
                "Open a kernel series and select a build first.", severity="warning"
            )
            return
        screen = PreviewOutputScreen(action, record, operation="Applying")
        self.push_screen(screen)
        self.run_worker(
            self.apply(action, record, screen), group="apply", exclusive=True
        )

    def show_apply_confirmation(self, action: PreviewAction) -> None:
        """Ask for a final explicit choice before applying a package action."""
        if not self.is_root:
            self.notify(
                "Package actions require launching the full program with sudo.",
                severity="warning",
            )
            return
        record = self.selected_record()
        if record is None:
            self.notify(
                "Open a kernel series and select a build first.", severity="warning"
            )
            return
        self.push_screen(
            ApplyConfirmationScreen(action, record),
            lambda confirmed: self.handle_apply_confirmation(confirmed, action),
        )

    def handle_apply_confirmation(
        self,
        confirmed: bool,
        action: PreviewAction,
    ) -> None:
        """Apply the selected action only after its confirmation popup accepts it."""
        if confirmed:
            self.start_apply(action)

    async def apply(
        self,
        action: PreviewAction,
        record: KernelRecord,
        screen: PreviewOutputScreen,
    ) -> None:
        """Apply an immediate apt action and stream its output to its modal."""
        try:
            command = apply_command(action, record)
        except ValueError as error:
            screen.dismiss()
            self.notify(str(error), severity="error")
            return
        screen.write_output(f"$ {' '.join(command)}")
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        assert process.stdout is not None
        while line := await process.stdout.readline():
            screen.write_output(line.decode(errors="replace").rstrip("\n"))
        screen.finish(await process.wait())
        self.action_reload()

    def action_show_help(self) -> None:
        self.push_screen(
            TextScreen(
                "kerntop 0.1.0 minimum viable manager",
                "Arrow keys: choose a row\n"
                "Enter: open the selected item\n"
                "Esc or Left: return to the series list; press Esc twice there to quit\n"
                "a: toggle recommended and all kernel variants\n"
                "p: preview the contextual package action\n"
                "i: install an available image\n"
                "d: remove an installed non-running image\n"
                "r: reload the local apt cache\n\n"
                "Install and remove actions require root mode and run immediately.",
            )
        )
