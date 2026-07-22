"""Screen for explicitly purging unused versioned kernel support packages."""

from textual.app import ComposeResult
from textual.containers import Container, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from ..kernels import PackageState


class HeaderCleanupScreen(ModalScreen[str | None]):
    """List detected unused kernel support packages by cleanup category."""

    BINDINGS = [("escape", "cancel", "Cancel"), ("q", "cancel", "Cancel")]

    def __init__(
        self,
        headers: tuple[PackageState, ...],
        support_packages: tuple[PackageState, ...],
    ) -> None:
        super().__init__()
        self.headers = headers
        self.support_packages = support_packages
        self.actions = (
            (
                f"Preview development-header purge ({len(headers)})",
                "preview-headers",
                not headers,
            ),
            (
                f"Purge development headers ({len(headers)})",
                "purge-headers",
                not headers,
            ),
            (
                f"Preview kernel-support purge ({len(support_packages)})",
                "preview-support",
                not support_packages,
            ),
            (
                f"Purge kernel support packages ({len(support_packages)})",
                "purge-support",
                not support_packages,
            ),
            ("Cancel", None, False),
        )

    def compose(self) -> ComposeResult:
        header_names = "\n".join(f"• {header.name}" for header in self.headers)
        support_names = "\n".join(
            f"• {package.name}" for package in self.support_packages
        )
        with Container(id="action-dialog"):
            yield Static("Kernel package cleanup", id="dialog-title")
            yield Static(
                f"Development headers: {len(self.headers)}\n"
                f"Kernel support packages: {len(self.support_packages)}"
            )
            with VerticalScroll(id="dialog-content"):
                if self.headers:
                    yield Static(f"Unused development headers\n{header_names}")
                if self.support_packages:
                    yield Static(f"Unused kernel support packages\n{support_names}")
            yield OptionList(
                *(
                    Option(label, disabled=disabled)
                    for label, _action, disabled in self.actions
                ),
                id="header-cleanup-actions",
            )
            yield Static(
                "This never runs autoremove. Preview first to inspect apt's plan.",
                id="dialog-help",
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "header-cleanup-actions":
            self.dismiss(self.actions[event.option_index][1])

    def action_cancel(self) -> None:
        self.dismiss()


class HeaderPurgeConfirmationScreen(ModalScreen[bool]):
    """Require a final confirmation before purging one cleanup category."""

    BINDINGS = [("escape", "cancel", "Cancel"), ("q", "cancel", "Cancel")]

    def __init__(self, package_label: str, packages: tuple[PackageState, ...]) -> None:
        super().__init__()
        self.package_label = package_label
        self.packages = packages

    def compose(self) -> ComposeResult:
        with Container(id="action-dialog"):
            yield Static(f"Confirm {self.package_label} purge", id="dialog-title")
            yield Static(
                f"This will purge {len(self.packages)} explicitly listed "
                f"{self.package_label} package(s). It does not run autoremove."
            )
            yield OptionList(
                "Cancel", f"Purge {self.package_label}", id="header-purge-confirmation"
            )
            yield Static(
                "Arrow keys choose an action; Enter confirms.", id="dialog-help"
            )

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        if event.option_list.id == "header-purge-confirmation":
            self.dismiss(event.option_index == 1)

    def action_cancel(self) -> None:
        self.dismiss(False)
