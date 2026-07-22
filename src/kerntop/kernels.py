"""Pure models and classification helpers for versioned kernel packages."""

from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Iterable


IMAGE_PREFIX = "linux-image-"
HEADER_PREFIX = "linux-headers-"
RELEASE_FLAVOUR_PATTERN = re.compile(r"^\d+(?:\.\d+)+(.*)$")


@dataclass(frozen=True)
class PackageState:
    """The package information kerntop needs from python-apt."""

    name: str
    architecture: str
    installed: bool
    installed_version: str | None
    candidate_version: str | None
    section: str | None = None


@dataclass(frozen=True)
class KernelRecord:
    """A selectable versioned kernel image and its relevant state."""

    package_name: str
    installed: bool
    installed_version: str | None
    candidate_version: str | None
    running: bool
    headers: tuple[PackageState, ...]

    @property
    def identifier(self) -> str:
        """Return the ABI/flavour portion of the image package name."""
        return self.package_name.removeprefix(IMAGE_PREFIX)


def kernel_identifier(package_name: str) -> str | None:
    """Return a versioned image identifier, excluding kernel meta packages."""
    if not package_name.startswith(IMAGE_PREFIX):
        return None
    identifier = package_name.removeprefix(IMAGE_PREFIX)
    if not identifier or not identifier[0].isdigit():
        return None
    return identifier


def is_kernel_meta_package(package_name: str) -> bool:
    """Identify linux-image meta packages, which are deliberately protected."""
    return package_name.startswith(IMAGE_PREFIX) and kernel_identifier(package_name) is None


def running_image_package(running_release: str) -> str:
    """Map ``uname -r`` output to the conventional image package name."""
    return f"{IMAGE_PREFIX}{running_release}"


def running_flavour(running_release: str) -> str:
    """Return the distribution/flavour suffix of a running kernel release."""
    match = RELEASE_FLAVOUR_PATTERN.match(running_release)
    return match.group(1) if match else ""


def is_relevant_image(package: PackageState, running_release: str) -> bool:
    """Keep installed images and available images matching the running flavour."""
    identifier = kernel_identifier(package.name)
    if identifier is None:
        return False
    elif package.section == "debug" or identifier.endswith("-dbg"):
        return False
    elif package.installed:
        return True
    else:
        flavour = running_flavour(running_release)
        return not flavour or identifier.endswith(flavour)


def matching_headers(
    image_package: str,
    packages: Iterable[PackageState],
) -> tuple[PackageState, ...]:
    """Return headers that belong to one versioned image package."""
    identifier = kernel_identifier(image_package)
    if identifier is None:
        return ()
    prefix = f"{HEADER_PREFIX}{identifier}"
    return tuple(package for package in packages if package.name.startswith(prefix))


def kernel_records(
    packages: Iterable[PackageState],
    native_architecture: str,
    running_release: str,
) -> tuple[KernelRecord, ...]:
    """Build kernel records from native-architecture python-apt package state."""
    native_packages = tuple(
        package for package in packages if package.architecture == native_architecture
    )
    running_package = running_image_package(running_release)
    records = []
    for package in native_packages:
        if not is_relevant_image(package, running_release):
            continue
        if not package.installed and package.candidate_version is None:
            continue
        records.append(
            KernelRecord(
                package_name=package.name,
                installed=package.installed,
                installed_version=package.installed_version,
                candidate_version=package.candidate_version,
                running=package.name == running_package,
                headers=matching_headers(package.name, native_packages),
            )
        )
    return tuple(sorted(records, key=lambda record: record.identifier, reverse=True))


def removal_is_blocked(record: KernelRecord) -> bool:
    """Return whether a record is unsafe to select for removal."""
    return record.running
