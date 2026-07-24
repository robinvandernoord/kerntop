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
) -> SimpleNamespace:
    return SimpleNamespace(
        architecture=architecture,
        version=version,
        section=section,
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
