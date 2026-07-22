"""Read-only kernel state backed by Debian's python-apt bindings."""

from __future__ import annotations

from dataclasses import dataclass
import os

from .apt_compat import import_apt_modules
from .kernels import KernelRecord, PackageState, kernel_records


@dataclass(frozen=True)
class KernelState:
    """The package state rendered by the POC interface."""

    native_architecture: str
    running_release: str
    records: tuple[KernelRecord, ...]


def package_states(cache: object) -> tuple[PackageState, ...]:
    """Convert an apt cache to the small, testable package representation."""
    states = []
    for package in cache:
        installed = package.installed
        candidate = package.candidate
        version = candidate or installed
        if version is None:
            continue
        states.append(
            PackageState(
                name=package.name,
                architecture=version.architecture,
                installed=installed is not None,
                installed_version=installed.version if installed else None,
                candidate_version=candidate.version if candidate else None,
                section=candidate.section if candidate else installed.section,
            )
        )
    return tuple(states)


def load_kernel_state() -> KernelState:
    """Load kernel image information from the local apt cache."""
    apt, apt_pkg = import_apt_modules()
    cache = apt.Cache()
    native_architecture = apt_pkg.config.find("APT::Architecture")
    running_release = os.uname().release
    records = kernel_records(
        package_states(cache),
        native_architecture,
        running_release,
    )
    return KernelState(native_architecture, running_release, records)
