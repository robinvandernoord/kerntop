from kerntop.kernels import (
    KernelRecord,
    KernelSeries,
    PackageState,
    has_non_running_fallback,
    is_relevant_image,
    kernel_identifier,
    kernel_series,
    matching_headers,
    removal_would_leave_no_fallback,
    running_flavour,
)


def package(
    name: str, *, installed: bool = False, section: str = "kernel"
) -> PackageState:
    return PackageState(
        name=name,
        architecture="amd64",
        installed=installed,
        installed_version="1.0" if installed else None,
        candidate_version="1.0",
        section=section,
    )


def record(name: str, installed: bool) -> KernelRecord:
    return KernelRecord(
        name,
        installed,
        "1.0" if installed else None,
        "1.0",
        False,
        (),
    )


def test_kernel_identifier_rejects_non_versioned_image_names() -> None:
    assert kernel_identifier("linux-headers-6.12") is None
    assert kernel_identifier("linux-image-") is None
    assert kernel_identifier("linux-image-generic") is None


def test_running_flavour_excludes_numeric_abi_revision() -> None:
    assert running_flavour("7.1.4-pikaos") == "-pikaos"
    assert running_flavour("6.8.0-134-generic") == "-generic"


def test_relevant_image_matches_generic_kernels_across_abi_revisions() -> None:
    available_generic = package("linux-image-6.8.0-135-generic")

    assert is_relevant_image(available_generic, "6.8.0-134-generic") is True


def test_fallback_detection_prevents_removing_the_only_alternate_kernel() -> None:
    running = KernelRecord(
        "linux-image-6.8.0-134-generic", True, "1.0", "1.0", True, ()
    )
    fallback = KernelRecord(
        "linux-image-6.8.0-135-generic", True, "1.0", "1.0", False, ()
    )
    additional_fallback = KernelRecord(
        "linux-image-6.8.0-136-generic", True, "1.0", "1.0", False, ()
    )

    assert has_non_running_fallback((running,)) is False
    assert has_non_running_fallback((running, fallback)) is True
    assert removal_would_leave_no_fallback((running, fallback), fallback) is True
    assert (
        removal_would_leave_no_fallback(
            (running, fallback, additional_fallback), fallback
        )
        is False
    )


def test_relevant_image_selection_covers_flavour_and_all_variant_rules() -> None:
    available_generic = package("linux-image-6.13.0-1-generic")
    available_cloud = package("linux-image-6.13.0-1-cloud")
    debug = package("linux-image-6.13.0-1-generic-dbg", section="debug")
    installed_cloud = package("linux-image-6.12.0-1-cloud", installed=True)

    assert is_relevant_image(available_generic, "6.12.0-1-generic") is True
    assert is_relevant_image(available_cloud, "6.12.0-1-generic") is False
    assert is_relevant_image(debug, "6.12.0-1-generic") is False
    assert is_relevant_image(installed_cloud, "6.12.0-1-generic") is True
    assert is_relevant_image(
        available_cloud, "6.12.0-1-generic", include_all_variants=True
    )


def test_matching_headers_rejects_meta_packages_and_matches_by_identifier() -> None:
    headers = (
        package("linux-headers-6.12.0-1-generic"),
        package("linux-headers-6.12.0-1-generic-extra"),
        package("linux-headers-6.11.0-1-generic"),
    )

    assert matching_headers("linux-image-generic", headers) == ()
    assert matching_headers("linux-image-6.12.0-1-generic", headers) == headers[:2]


def test_kernel_series_groups_sorts_and_counts_records() -> None:
    series = kernel_series(
        (
            record("linux-image-6.12.0-1-generic", installed=True),
            record("linux-image-6.12.1-1-generic", installed=False),
            record("linux-image-6.9.0-1-generic", installed=True),
            record("linux-image-custom", installed=False),
        )
    )

    assert series == (
        KernelSeries("6.9", (record("linux-image-6.9.0-1-generic", installed=True),)),
        KernelSeries(
            "6.12",
            (
                record("linux-image-6.12.0-1-generic", installed=True),
                record("linux-image-6.12.1-1-generic", installed=False),
            ),
        ),
    )
    assert series[1].installed_count == 1
    assert series[1].available_count == 1
