"""Screens for actions on one kernel image."""

from dataclasses import dataclass

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static

from ..apt_commands import PreviewAction
from ..kernels import KernelRecord


@dataclass(frozen=True)
class KernelAction:
    """An action available for the currently selected kernel image."""

    label: str
    action: PreviewAction
    applies_changes: bool
    queues_changes: bool = False


class KernelActionsScreen(ModalScreen[KernelAction | None]):
    """A context-aware action prompt for one kernel image."""

    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close")]

    def __init__(
        self,
        record: KernelRecord,
        can_change_packages: bool,
        removes_final_fallback: bool,
    ) -> None:
        super().__init__()
        self.record = record
        self.can_change_packages = can_change_packages
        self.removes_final_fallback = removes_final_fallback
        if can_change_packages and not record.installed:
            self.actions = (
                KernelAction("Preview installation", PreviewAction.INSTALL, False),
                KernelAction("Install", PreviewAction.INSTALL, True),
                KernelAction("Queue installation", PreviewAction.INSTALL, False, True),
            )
        elif can_change_packages and record.installed and not record.running:
            self.actions = (
                KernelAction("Preview removal", PreviewAction.REMOVE, False),
                KernelAction("Remove", PreviewAction.REMOVE, True),
                KernelAction("Preview purge", PreviewAction.PURGE, False),
                KernelAction("Purge", PreviewAction.PURGE, True),
                KernelAction("Queue removal", PreviewAction.REMOVE, False, True),
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
        if not self.can_change_packages:
            details += "\n\nRun kerntop with sudo to enable package actions."
        elif self.record.running:
            details += "\n\nThe running kernel cannot be removed."
        elif self.record.installed:
            details += (
                "\n\nRemove keeps this package's configuration."
                "\nPurge also removes that configuration."
                "\nHeaders and kernel support packages are managed separately.\n"
            )
            if self.removes_final_fallback:
                details += (
                    "\nWARNING: this is the final non-running fallback kernel. "
                    "Removing it leaves no alternate installed kernel."
                )
        with Container(id="action-dialog"):
            yield Static("Kernel actions", id="dialog-title")
            yield Static(details)
            if self.actions:
                yield OptionList(
                    *(action.label for action in self.actions), id="kernel-actions"
                )
                yield Static(
                    "Arrow keys choose an action; Enter confirms.", id="dialog-help"
                )
            else:
                yield Static("Esc or q closes this view.", id="dialog-help")

    def on_mount(self) -> None:
        if self.actions:
            self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "kernel-actions":
            self.dismiss(self.actions[event.option_index])

    def action_close(self) -> None:
        self.dismiss()


class ApplyConfirmationScreen(ModalScreen[bool]):
    """Require an explicit choice before changing installed packages."""

    BINDINGS = [("escape", "cancel", "Cancel"), ("q", "cancel", "Cancel")]

    def __init__(
        self,
        action: PreviewAction,
        record: KernelRecord,
        removes_final_fallback: bool,
    ) -> None:
        super().__init__()
        self.action = action
        self.record = record
        self.removes_final_fallback = removes_final_fallback

    def compose(self) -> ComposeResult:
        with Container(id="action-dialog"):
            yield Static(f"Confirm {self.action.value}", id="dialog-title")
            warning = (
                "\n\nWARNING: this removes the final non-running fallback kernel. "
                "No alternate installed kernel will remain."
                if self.removes_final_fallback
                else ""
            )
            yield Static(
                f"{self.record.identifier}\n\nThis will change packages on this host using apt-get."
                f"{warning}"
            )
            yield OptionList(
                "Cancel", f"Apply {self.action.value}", id="apply-confirmation"
            )
            yield Static(
                "Arrow keys choose an action; Enter confirms.", id="dialog-help"
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "apply-confirmation":
            self.dismiss(event.option_index == 1)

    def action_cancel(self) -> None:
        self.dismiss(False)
