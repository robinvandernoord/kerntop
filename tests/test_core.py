from pathlib import Path

import pytest

from kerntop.apt_commands import PreviewAction, preview_command
from kerntop.apt_compat import available_apt_pkg_abis, system_site_paths
from kerntop.kernels import (
    KernelRecord,
    PackageState,
    is_kernel_meta_package,
    kernel_records,
    running_image_package,
)


def package(
    name: str,
    installed: bool = False,
    candidate_version: str | None = "1.0",
    section: str | None = "kernel",
) -> PackageState:
    return PackageState(
        name=name,
        architecture="amd64",
        installed=installed,
        installed_version="1.0" if installed else None,
        candidate_version=candidate_version,
        section=section,
    )


def test_kernel_records_mark_running_image_and_match_headers() -> None:
    records = kernel_records(
        (
            package("linux-image-6.12.0-1-generic", installed=True),
            package("linux-headers-6.12.0-1-generic", installed=True),
            package("linux-image-generic", installed=True),
            package("linux-image-6.11.0-1-generic"),
            PackageState("linux-image-6.12.0-1-arm64", "arm64", False, None, "1.0"),
        ),
        "amd64",
        "6.12.0-1-generic",
    )

    assert [record.package_name for record in records] == [
        "linux-image-6.12.0-1-generic",
        "linux-image-6.11.0-1-generic",
    ]
    assert records[0].running is True
    assert records[0].headers[0].name == "linux-headers-6.12.0-1-generic"


def test_meta_packages_are_not_versioned_images() -> None:
    assert is_kernel_meta_package("linux-image-generic") is True
    assert is_kernel_meta_package("linux-image-6.12.0-1-generic") is False
    assert running_image_package("6.12.0-1-generic") == "linux-image-6.12.0-1-generic"


def test_kernel_records_prefer_running_flavour_and_hide_debug_images() -> None:
    records = kernel_records(
        (
            package("linux-image-7.1.2-pikaos", installed=True),
            package("linux-image-7.1.3-pikaos"),
            package("linux-image-7.1.3-pikaos-dbg", section="debug"),
            package("linux-image-7.1.3-amd64"),
            package("linux-image-7.1.3-amd64-unsigned"),
            package("linux-image-7.1.2-amd64", installed=True),
        ),
        "amd64",
        "7.1.2-pikaos",
    )

    assert [record.package_name for record in records] == [
        "linux-image-7.1.3-pikaos",
        "linux-image-7.1.2-pikaos",
        "linux-image-7.1.2-amd64",
    ]


def test_running_kernel_cannot_be_previewed_for_removal() -> None:
    record = KernelRecord(
        "linux-image-6.12.0-1-generic",
        True,
        "1.0",
        "1.0",
        True,
        (),
    )

    with pytest.raises(ValueError, match="currently running"):
        preview_command(PreviewAction.REMOVE, record)


def test_preview_command_is_always_a_simulation() -> None:
    record = KernelRecord(
        "linux-image-6.11.0-1-generic",
        True,
        "1.0",
        "1.0",
        False,
        (),
    )

    assert preview_command(PreviewAction.INSTALL, record) == (
        "apt-get",
        "--simulate",
        "install",
        "linux-image-6.11.0-1-generic",
    )
    assert preview_command(PreviewAction.REMOVE, record) == (
        "apt-get",
        "--simulate",
        "remove",
        "linux-image-6.11.0-1-generic",
    )


def test_system_paths_and_abi_detection(tmp_path: Path) -> None:
    paths = system_site_paths((3, 13), (str(tmp_path),))
    assert paths == (
        tmp_path / "lib/python3.13/dist-packages",
        tmp_path / "lib/python3/dist-packages",
    )

    site_packages = paths[0]
    site_packages.mkdir(parents=True)
    (site_packages / "apt_pkg.cpython-313-x86_64-linux-gnu.so").touch()
    (site_packages / "apt_pkg.cpython-314-x86_64-linux-gnu.so").touch()

    assert available_apt_pkg_abis(paths) == ("313", "314")
