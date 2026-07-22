"""Generic modal screens."""

import typing as t

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Log, Static


class TextScreen(ModalScreen[None]):
    """A scrollable modal used for help text."""

    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close")]

    def __init__(self, title: str, content: str) -> None:
        super().__init__()
        self.dialog_title = title
        self.content = content

    def compose(self) -> ComposeResult:
        with Container(id="text-dialog"):
            yield Static(self.dialog_title, id="dialog-title")
            with VerticalScroll(id="dialog-content"):
                yield Static(self.content)
            yield Static("Esc or q closes this view.", id="dialog-help")

    def action_close(self) -> None:
        self.dismiss()


class PreviewOutputScreen(ModalScreen[None]):
    """Show live apt output for a preview or transaction."""

    BINDINGS = [("escape", "close", "Close"), ("q", "close", "Close")]

    def __init__(
        self, title: str, on_finished: t.Callable[[int], None] | None = None
    ) -> None:
        super().__init__()
        self.dialog_title = title
        self.on_finished = on_finished
        self.pending_output: list[str] = []
        self.pending_return_code: int | None = None

    def compose(self) -> ComposeResult:
        with Container(id="text-dialog"):
            yield Static(self.dialog_title, id="dialog-title")
            yield Log(auto_scroll=True, id="apt-output")
            yield Static("Running apt-get…", id="apt-status")
            yield Static("Esc or q closes this view.", id="dialog-help")

    def write_output(self, line: str) -> None:
        if not self.is_mounted:
            self.pending_output.append(line)
            return
        self.query_one("#apt-output", Log).write_line(line)

    def finish(self, return_code: int) -> None:
        if not self.is_mounted:
            self.pending_return_code = return_code
            return
        status = self.query_one("#apt-status", Static)
        status.update(f"apt-get finished with exit status {return_code}.")
        status.add_class("success" if return_code == 0 else "failure")
        if self.on_finished is not None:
            self.on_finished(return_code)

    def on_mount(self) -> None:
        for line in self.pending_output:
            self.query_one("#apt-output", Log).write_line(line)
        self.pending_output = []
        if self.pending_return_code is not None:
            return_code = self.pending_return_code
            self.pending_return_code = None
            self.finish(return_code)

    def action_close(self) -> None:
        self.dismiss()
