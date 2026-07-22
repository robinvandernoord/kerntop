"""Construction and execution of non-mutating apt-get previews."""

from __future__ import annotations

import asyncio
import subprocess
import typing as t
from dataclasses import dataclass
from enum import StrEnum

from .kernels import (
    KERNEL_SUPPORT_PREFIXES,
    KernelRecord,
    PackageState,
    removal_is_blocked,
)


class PreviewAction(StrEnum):
    """The package transaction previews supported by the POC."""

    INSTALL = "install"
    REMOVE = "remove"
    PURGE = "purge"


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
    if action in (PreviewAction.REMOVE, PreviewAction.PURGE) and removal_is_blocked(
        record
    ):
        raise ValueError("The currently running kernel cannot be removed.")
    if action in (PreviewAction.REMOVE, PreviewAction.PURGE) and not record.installed:
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
    if action in (PreviewAction.REMOVE, PreviewAction.PURGE) and removal_is_blocked(
        record
    ):
        raise ValueError("The currently running kernel cannot be removed.")
    elif action in (PreviewAction.REMOVE, PreviewAction.PURGE) and not record.installed:
        raise ValueError("Only installed kernels can be removed.")
    elif action is PreviewAction.INSTALL and record.installed:
        raise ValueError("This kernel image is already installed.")
    elif action in (
        PreviewAction.INSTALL,
        PreviewAction.REMOVE,
        PreviewAction.PURGE,
    ):
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


def header_purge_command(
    headers: t.Iterable[PackageState], simulate: bool = True
) -> tuple[str, ...]:
    """Build an apt purge command for explicitly selected unused headers."""
    selected_headers = tuple(headers)
    if not selected_headers:
        raise ValueError("Select at least one unused header package.")
    if any(
        not package.installed
        or not package.name.startswith("linux-headers-")
        or not package.name.removeprefix("linux-headers-")[:1].isdigit()
        for package in selected_headers
    ):
        raise ValueError("Only installed versioned header packages can be purged.")
    options = ("--simulate",) if simulate else ("--assume-yes",)
    return (
        "apt-get",
        *options,
        "purge",
        *(package.name for package in selected_headers),
    )


def support_package_purge_command(
    packages: t.Iterable[PackageState], simulate: bool = True
) -> tuple[str, ...]:
    """Build an apt purge command for explicit versioned kernel support packages."""
    selected_packages = tuple(packages)
    if not selected_packages:
        raise ValueError("Select at least one unused kernel support package.")
    if any(
        not package.installed
        or not package.name.startswith(KERNEL_SUPPORT_PREFIXES)
        or not any(
            package.name.removeprefix(prefix)[:1].isdigit()
            for prefix in KERNEL_SUPPORT_PREFIXES
            if package.name.startswith(prefix)
        )
        for package in selected_packages
    ):
        raise ValueError(
            "Only installed versioned kernel support packages can be purged."
        )
    options = ("--simulate",) if simulate else ("--assume-yes",)
    return (
        "apt-get",
        *options,
        "purge",
        *(package.name for package in selected_packages),
    )


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
