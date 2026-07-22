"""Construction and execution of non-mutating apt-get previews."""

from __future__ import annotations

import asyncio
import subprocess
import typing as t
from dataclasses import dataclass
from enum import StrEnum

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


@dataclass(frozen=True)
class QueuedAction:
    """One package change staged for a combined apt transaction."""

    action: PreviewAction
    record: KernelRecord


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


def apply_command(action: PreviewAction, record: KernelRecord) -> tuple[str, ...]:
    """Build a single-record apt-get transaction command."""
    if action is PreviewAction.REMOVE and removal_is_blocked(record):
        raise ValueError("The currently running kernel cannot be removed.")
    elif action is PreviewAction.REMOVE and not record.installed:
        raise ValueError("Only installed kernels can be removed.")
    elif action is PreviewAction.INSTALL and record.installed:
        raise ValueError("This kernel image is already installed.")
    elif action is PreviewAction.INSTALL or action is PreviewAction.REMOVE:
        return ("apt-get", "--assume-yes", action.value, record.package_name)
    else:
        raise ValueError(f"Unsupported kernel action: {action}")


def transaction_command(
    actions: t.Iterable[QueuedAction], simulate: bool = True
) -> tuple[str, ...]:
    """Build one apt command for staged installs and removals.

    Simulations are the default. Apt accepts ``package-`` as a removal request
    alongside installation targets, keeping all selected changes in one
    transaction.
    """
    queued_actions = tuple(actions)
    if not queued_actions:
        raise ValueError("There are no queued package actions.")

    targets = []
    seen_packages: set[str] = set()
    for queued_action in queued_actions:
        action = queued_action.action
        record = queued_action.record
        if record.package_name in seen_packages:
            raise ValueError("A kernel package can only appear once in the queue.")
        seen_packages.add(record.package_name)
        if action is PreviewAction.REMOVE:
            if removal_is_blocked(record):
                raise ValueError("The currently running kernel cannot be removed.")
            elif not record.installed:
                raise ValueError("Only installed kernels can be removed.")
            targets.append(f"{record.package_name}-")
        elif action is PreviewAction.INSTALL:
            if record.installed:
                raise ValueError("Installed kernels cannot be queued for installation.")
            targets.append(record.package_name)
        else:
            raise ValueError(f"Unsupported kernel action: {action}")

    options = ("--simulate",) if simulate else ("--assume-yes",)
    return ("apt-get", *options, "install", *targets)


async def stream_command(
    command: tuple[str, ...], write_line: t.Callable[[str], None]
) -> int:
    """Run an apt command and send its combined output to ``write_line``."""
    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    assert process.stdout is not None
    while line := await process.stdout.readline():
        write_line(line.decode(errors="replace").rstrip("\n"))
    return await process.wait()
