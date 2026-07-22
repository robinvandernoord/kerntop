"""Construction and execution of non-mutating apt-get previews."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
import subprocess


from .kernels import KernelRecord, removal_is_blocked


class PreviewAction(StrEnum):
    """The package transaction previews supported by the POC."""

    INSTALL = "install"
    REMOVE = "remove"


@dataclass(frozen=True)
class PreviewResult:
    """Captured output from an ``apt-get --simulate`` command."""

    command: tuple[str, ...]
    return_code: int
    output: str


def preview_command(action: PreviewAction, record: KernelRecord) -> tuple[str, ...]:
    """Build a safe apt-get simulation command for a kernel record."""
    if action is PreviewAction.REMOVE and removal_is_blocked(record):
        raise ValueError("The currently running kernel cannot be removed.")
    if action is PreviewAction.REMOVE and not record.installed:
        raise ValueError("Only installed kernels can be removed.")
    return ("apt-get", "--simulate", action.value, record.package_name)


def run_preview(action: PreviewAction, record: KernelRecord) -> PreviewResult:
    """Run an apt-get simulation and capture combined terminal output."""
    command = preview_command(action, record)
    completed = subprocess.run(
        command,
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    return PreviewResult(command, completed.returncode, completed.stdout)
