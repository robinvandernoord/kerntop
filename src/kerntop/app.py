"""Textual interface for the kerntop proof of concept."""

import asyncio
import os
import typing as t

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.widgets import DataTable, Footer, Header, Static

from .apt_commands import (
    PreviewAction,
    QueuedAction,
    apply_command,
    header_purge_command,
    preview_command,
    stream_command,
    support_package_purge_command,
    transaction_command,
)
from .apt_compat import AptUnavailableError
from .apt_state import KernelState, load_kernel_state
from .kernels import (
    KernelRecord,
    KernelSeries,
    PackageState,
    has_non_running_fallback,
    kernel_records,
    kernel_series,
    removal_would_leave_no_fallback,
    unused_headers,
    unused_kernel_support_packages,
)
from .screens.header_cleanup import HeaderCleanupScreen, HeaderPurgeConfirmationScreen
from .screens.kernel_actions import (
    ApplyConfirmationScreen,
    KernelAction,
    KernelActionsScreen,
)
from .screens.modal import PreviewOutputScreen, TextScreen
from .screens.queue import QueueApplyConfirmationScreen, QueueScreen


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
    #kernel-actions, #apply-confirmation, #queue-actions, #queue-confirmation {
        border: none;
        padding: 0;
    }
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
        Binding("q", "queue_install_selected", "Queue install"),
        Binding("q", "queue_remove_selected", "Queue removal", priority=True),
        ("i", "install_selected", "Install"),
        ("d", "remove_selected", "Remove"),
        ("c", "view_queue", "Queue"),
        ("u", "header_cleanup", "Header cleanup"),
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
        self.queued_actions: tuple[QueuedAction, ...] = ()
        self.unused_header_packages: tuple[PackageState, ...] = ()
        self.unused_kernel_support_packages: tuple[PackageState, ...] = ()

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
            self.unused_header_packages = ()
            self.unused_kernel_support_packages = ()
            self.render_error(str(error))
            return
        except Exception as error:
            self.records = ()
            self.unused_header_packages = ()
            self.unused_kernel_support_packages = ()
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
        self.unused_header_packages = unused_headers(
            self.packages, self.native_architecture
        )
        self.unused_kernel_support_packages = unused_kernel_support_packages(
            self.packages, self.native_architecture
        )
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

    def fallback_warning(self) -> str:
        """Return the persistent warning used when no fallback kernel exists."""
        if has_non_running_fallback(self.records):
            return ""
        return (
            "\n[bold yellow]WARNING: no non-running fallback kernel is installed.[/]\n"
        )

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
        cleanup_package_count = len(self.unused_header_packages) + len(
            self.unused_kernel_support_packages
        )
        header_cleanup = (
            f" {cleanup_package_count} unused kernel support package(s): press u to review."
            if cleanup_package_count
            else ""
        )
        fallback_warning = self.fallback_warning()
        self.query_one("#summary", Static).update(
            f"{len(self.series)} kernel series for {self.native_architecture}; "
            f"running: {self.running_release}. "
            f"Showing {'all variants' if self.show_all_variants else 'recommended variants'}. "
            f"Press Enter to view builds.{fallback_warning}{header_cleanup}"
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
            f"Press Enter for actions.{self.fallback_warning()}"
        )
        self.refresh_bindings()

    def check_action(self, action: str, parameters: tuple[t.Any, ...]) -> bool | None:
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
        elif action == "queue_install_selected":
            return self.is_root and record is not None and not record.installed
        elif action == "remove_selected":
            return (
                self.is_root
                and record is not None
                and record.installed
                and not record.running
            )
        elif action == "queue_remove_selected":
            return (
                self.is_root
                and record is not None
                and record.installed
                and not record.running
            )
        elif action == "view_queue":
            return self.is_root and bool(self.queued_actions)
        elif action == "header_cleanup":
            return (
                self.is_root
                and self.active_series is None
                and bool(
                    self.unused_header_packages or self.unused_kernel_support_packages
                )
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
            KernelActionsScreen(
                record,
                self.is_root,
                removal_would_leave_no_fallback(self.records, record),
            ),
            self.handle_kernel_action,
        )

    def handle_kernel_action(self, action: KernelAction | None) -> None:
        """Run, queue, or preview the selected kernel action."""
        if action is not None:
            if action.queues_changes:
                self.queue_action(action.action)
            elif action.applies_changes:
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

    def action_queue_install_selected(self) -> None:
        """Queue installation of the highlighted available image."""
        self.queue_action(PreviewAction.INSTALL)

    def action_remove_selected(self) -> None:
        """Confirm removal of the highlighted installed image."""
        self.show_apply_confirmation(PreviewAction.REMOVE)

    def action_queue_remove_selected(self) -> None:
        """Queue removal of the highlighted installed image."""
        self.queue_action(PreviewAction.REMOVE)

    def queue_action(self, action: PreviewAction) -> None:
        """Stage the selected safe package action without changing the host."""
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
        if any(
            item.record.package_name == record.package_name
            for item in self.queued_actions
        ):
            self.notify("That kernel is already in the queue.", severity="warning")
            return
        self.queued_actions += (QueuedAction(action, record),)
        self.notify(f"Queued {action.value}: {record.identifier}.")
        self.refresh_bindings()

    def action_view_queue(self) -> None:
        """Review, simulate, or apply the staged package transaction."""
        if not self.queued_actions:
            self.notify("There are no queued package actions.", severity="warning")
            return
        self.push_screen(
            QueueScreen(self.queued_actions),
            self.handle_queue_action,
        )

    def action_header_cleanup(self) -> None:
        """Review installed headers that no longer match an installed image."""
        if not (self.unused_header_packages or self.unused_kernel_support_packages):
            self.notify("There are no unused kernel support packages.")
            return
        self.push_screen(
            HeaderCleanupScreen(
                self.unused_header_packages, self.unused_kernel_support_packages
            ),
            self.handle_header_cleanup_action,
        )

    def handle_header_cleanup_action(self, action: str | None) -> None:
        if action == "preview-headers":
            self.start_header_purge(simulate=True)
        elif action == "purge-headers":
            self.push_screen(
                HeaderPurgeConfirmationScreen(
                    "development headers", self.unused_header_packages
                ),
                self.handle_header_purge_confirmation,
            )
        elif action == "preview-support":
            self.start_kernel_support_purge(simulate=True)
        elif action == "purge-support":
            self.push_screen(
                HeaderPurgeConfirmationScreen(
                    "kernel support", self.unused_kernel_support_packages
                ),
                self.handle_kernel_support_purge_confirmation,
            )

    def handle_header_purge_confirmation(self, confirmed: bool | None) -> None:
        if confirmed:
            self.start_header_purge(simulate=False)

    def start_header_purge(self, simulate: bool) -> None:
        """Preview or purge the currently detected unused headers."""
        operation = "Simulating" if simulate else "Purging"
        callback = None if simulate else self.handle_header_purge_finished
        screen = PreviewOutputScreen(
            f"{operation} unused development headers", callback
        )
        self.push_screen(screen)
        self.run_worker(
            self.purge_headers(screen, simulate),
            group="header-purge",
            exclusive=True,
        )

    def handle_header_purge_finished(self, return_code: int) -> None:
        if return_code == 0:
            self.action_reload()

    async def purge_headers(self, screen: PreviewOutputScreen, simulate: bool) -> None:
        """Run the explicit header purge and stream its apt output."""
        try:
            command = header_purge_command(
                self.unused_header_packages, simulate=simulate
            )
        except ValueError as error:
            screen.dismiss()
            self.notify(str(error), severity="error")
            return
        screen.write_output(f"$ {' '.join(command)}")
        screen.finish(await stream_command(command, screen.write_output))

    def handle_kernel_support_purge_confirmation(self, confirmed: bool | None) -> None:
        if confirmed:
            self.start_kernel_support_purge(simulate=False)

    def start_kernel_support_purge(self, simulate: bool) -> None:
        """Preview or purge the detected unused kernel support packages."""
        operation = "Simulating" if simulate else "Purging"
        callback = None if simulate else self.handle_kernel_support_purge_finished
        screen = PreviewOutputScreen(
            f"{operation} unused kernel support packages", callback
        )
        self.push_screen(screen)
        self.run_worker(
            self.purge_kernel_support_packages(screen, simulate),
            group="kernel-support-purge",
            exclusive=True,
        )

    def handle_kernel_support_purge_finished(self, return_code: int) -> None:
        if return_code == 0:
            self.action_reload()

    async def purge_kernel_support_packages(
        self, screen: PreviewOutputScreen, simulate: bool
    ) -> None:
        """Run the explicit kernel support purge and stream its apt output."""
        try:
            command = support_package_purge_command(
                self.unused_kernel_support_packages, simulate=simulate
            )
        except ValueError as error:
            screen.dismiss()
            self.notify(str(error), severity="error")
            return
        screen.write_output(f"$ {' '.join(command)}")
        screen.finish(await stream_command(command, screen.write_output))

    def handle_queue_action(self, action: str | None) -> None:
        if action == "clear":
            self.queued_actions = ()
            self.notify("Cleared queued package actions.")
            self.refresh_bindings()
        elif action == "simulate":
            self.start_queued_transaction(simulate=True)
        elif action == "apply":
            self.push_screen(
                QueueApplyConfirmationScreen(
                    self.queued_actions,
                    any(
                        queued_action.action is PreviewAction.REMOVE
                        and removal_would_leave_no_fallback(
                            self.records, queued_action.record
                        )
                        for queued_action in self.queued_actions
                    ),
                ),
                self.handle_queue_apply_confirmation,
            )

    def handle_queue_apply_confirmation(self, confirmed: bool | None) -> None:
        if confirmed:
            self.start_queued_transaction(simulate=False)

    def start_queued_transaction(self, simulate: bool) -> None:
        """Preview or run the queued changes and stream apt output live."""
        operation = "Simulating" if simulate else "Applying"
        callback = None if simulate else self.handle_queue_apply_finished
        screen = PreviewOutputScreen(f"{operation} queued changes", callback)
        self.push_screen(screen)
        self.run_worker(
            self.run_queued_transaction(screen, simulate),
            group="queued-transaction",
            exclusive=True,
        )

    def handle_queue_apply_finished(self, return_code: int) -> None:
        if return_code == 0:
            self.queued_actions = ()
            self.action_reload()
        self.refresh_bindings()

    async def run_queued_transaction(
        self, screen: PreviewOutputScreen, simulate: bool
    ) -> None:
        try:
            command = transaction_command(self.queued_actions, simulate=simulate)
        except ValueError as error:
            screen.dismiss()
            self.notify(str(error), severity="error")
            return
        screen.write_output(f"$ {' '.join(command)}")
        screen.finish(await stream_command(command, screen.write_output))

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
        screen = PreviewOutputScreen(f"Simulating {action.value}: {record.identifier}")
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
        screen.finish(await stream_command(command, screen.write_output))

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
        screen = PreviewOutputScreen(f"Applying {action.value}: {record.identifier}")
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
            ApplyConfirmationScreen(
                action,
                record,
                action in (PreviewAction.REMOVE, PreviewAction.PURGE)
                and removal_would_leave_no_fallback(self.records, record),
            ),
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
        screen.finish(await stream_command(command, screen.write_output))
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
                "q: queue the contextual package action\n"
                "i: install an available image\n"
                "d: remove an installed non-running image\n"
                "c: review queued package actions\n"
                "u: review unused development headers (main browser only)\n"
                "r: reload the local apt cache\n\n"
                "Install and remove actions require root mode and run immediately. "
                "Queued actions can be previewed before their final confirmation.",
            )
        )
