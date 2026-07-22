from pathlib import Path

from kerntop.apt_compat import available_apt_pkg_abis, system_site_paths


def test_system_site_paths_deduplicates_prefixes(tmp_path: Path) -> None:
    assert system_site_paths((3, 13), (str(tmp_path), str(tmp_path))) == (
        tmp_path / "lib/python3.13/dist-packages",
        tmp_path / "lib/python3/dist-packages",
    )


def test_available_apt_pkg_abis_ignores_non_apt_extensions(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    for filename in (
        "apt_pkg.cpython-312-x86_64-linux-gnu.so",
        "apt_pkg.cpython-313-aarch64-linux-gnu.so",
        "apt_pkg.cpython-313-x86_64-linux-gnu.txt",
        "apt_pkg.not-cpython.so",
    ):
        (tmp_path / filename).touch()

    assert available_apt_pkg_abis((tmp_path, Path("/does/not/exist"))) == (
        "312",
        "313",
    )
