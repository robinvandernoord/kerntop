from types import SimpleNamespace

from kerntop.apt_state import package_states
from kerntop.kernels import PackageState


def apt_package(
    name: str,
    *,
    installed: SimpleNamespace | None = None,
    candidate: SimpleNamespace | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(name=name, installed=installed, candidate=candidate)


def version(
    architecture: str = "amd64",
    version: str = "1.0",
    section: str = "kernel",
    dependencies: tuple[SimpleNamespace, ...] = (),
) -> SimpleNamespace:
    return SimpleNamespace(
        architecture=architecture,
        version=version,
        section=section,
        dependencies=dependencies,
    )


def dependency(rawtype: str, names: tuple[str, ...]) -> SimpleNamespace:
    return SimpleNamespace(
        rawtype=rawtype,
        or_dependencies=tuple(SimpleNamespace(name=name) for name in names),
    )


def test_package_states_filters_packages_and_preserves_apt_metadata() -> None:
    assert package_states(
        (
            apt_package(
                "linux-image-6.12",
                installed=version(version="old"),
                candidate=version(version="new", section="kernel/extra"),
            ),
            apt_package(
                "linux-headers-6.12",
                installed=version(version="headers"),
            ),
            apt_package("bash", candidate=version()),
            apt_package("linux-image-no-version"),
        )
    ) == (
        PackageState(
            "linux-image-6.12",
            "amd64",
            True,
            "old",
            "new",
            "kernel/extra",
        ),
        PackageState("linux-headers-6.12", "amd64", True, "headers", None, "kernel"),
    )


def test_package_states_keeps_candidate_only_packages() -> None:
    states = package_states(
        (
            apt_package(
                "linux-image-6.13",
                candidate=version(architecture="arm64", version="candidate"),
            ),
            apt_package("linux-image-6.14"),
        )
    )

    assert states == (
        PackageState(
            "linux-image-6.13",
            "arm64",
            False,
            None,
            "candidate",
            "kernel",
        ),
    )


def test_package_states_reads_meta_package_image_dependencies() -> None:
    meta_version = version(
        dependencies=(
            dependency("Depends", ("linux-image-6.14.0-15-generic",)),
            dependency("Recommends", ("linux-image-6.14.0-15-generic-hwe",)),
            dependency("Depends", ("initramfs-tools",)),
        )
    )

    states = package_states(
        (
            apt_package(
                "linux-image-generic",
                installed=meta_version,
                candidate=meta_version,
            ),
        )
    )

    assert states == (
        PackageState(
            "linux-image-generic",
            "amd64",
            True,
            "1.0",
            "1.0",
            "kernel",
            ("linux-image-6.14.0-15-generic", "initramfs-tools"),
        ),
    )
