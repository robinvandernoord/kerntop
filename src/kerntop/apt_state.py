"""Read-only kernel state backed by Debian's python-apt bindings."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .apt_compat import import_apt_modules
from .kernels import (
    HEADER_PREFIX,
    IMAGE_PREFIX,
    KernelRecord,
    PackageState,
    kernel_records,
)


@dataclass(frozen=True)
class KernelState:
    """The package state rendered by the POC interface."""

    native_architecture: str
    running_release: str
    packages: tuple[PackageState, ...]
    records: tuple[KernelRecord, ...]


def package_states(cache: object) -> tuple[PackageState, ...]:
    """Convert an apt cache to the small, testable package representation."""
    states = []
    for package in cache:
        if not package.name.startswith((IMAGE_PREFIX, HEADER_PREFIX)):
            continue
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


def load_kernel_state(include_all_variants: bool = False) -> KernelState:
    """Load recommended or all kernel image variants from the local apt cache."""
    apt, apt_pkg = import_apt_modules()
    cache = apt.Cache()
    native_architecture = apt_pkg.config.find("APT::Architecture")
    running_release = os.uname().release
    packages = package_states(cache)
    records = kernel_records(
        packages,
        native_architecture,
        running_release,
        include_all_variants=include_all_variants,
    )
    return KernelState(native_architecture, running_release, packages, records)
