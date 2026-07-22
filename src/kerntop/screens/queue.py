"""Screens for reviewing and confirming queued package changes."""

from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static

from ..apt_commands import QueuedAction


class QueueScreen(ModalScreen[str | None]):
    """Show staged package changes and offer the queue workflow."""

    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close")]

    def __init__(self, actions: tuple[QueuedAction, ...]) -> None:
        super().__init__()
        self.actions = actions

    def compose(self) -> ComposeResult:
        changes = "\n".join(
            f"{action.action.value}: {action.record.identifier}"
            for action in self.actions
        )
        options = [
            "Close",
            "Clear queue",
            "Preview queued actions",
            "Run queued actions",
        ]
        with Container(id="action-dialog"):
            yield Static("Queued kernel changes", id="dialog-title")
            yield Static(changes)
            yield OptionList(*options, id="queue-actions")
            yield Static(
                "Preview first to inspect apt's package plan before running changes.",
                id="dialog-help",
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "queue-actions":
            self.dismiss(("close", "clear", "simulate", "apply")[event.option_index])

    def action_close(self) -> None:
        self.dismiss()


class QueueApplyConfirmationScreen(ModalScreen[bool]):
    """Require a final choice before applying a queued transaction."""

    BINDINGS = [("escape", "cancel", "Cancel"), ("q", "cancel", "Cancel")]

    def __init__(self, actions: tuple[QueuedAction, ...]) -> None:
        super().__init__()
        self.actions = actions

    def compose(self) -> ComposeResult:
        changes = "\n".join(
            f"{action.action.value}: {action.record.identifier}"
            for action in self.actions
        )
        with Container(id="action-dialog"):
            yield Static("Apply queued kernel changes", id="dialog-title")
            yield Static(
                f"{changes}\n\nThis will change packages on this host using apt-get."
            )
            yield OptionList("Cancel", "Apply queued changes", id="queue-confirmation")
            yield Static(
                "Arrow keys choose an action; Enter confirms.", id="dialog-help"
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "queue-confirmation":
            self.dismiss(event.option_index == 1)

    def action_cancel(self) -> None:
        self.dismiss(False)
