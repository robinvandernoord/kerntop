"""Compatibility helpers for importing Debian's python-apt bindings."""

from __future__ import annotations

import importlib
import re
import sys
from pathlib import Path
from types import ModuleType
from typing import Iterable


class AptUnavailableError(RuntimeError):
    """Raised when the distro-provided python-apt bindings cannot be imported."""


def system_site_paths(
    version: tuple[int, int] | None = None,
    prefixes: Iterable[str] = ("/usr", "/usr/local"),
) -> tuple[Path, ...]:
    """Return likely distro site-package directories for the active Python."""
    major, minor = version or sys.version_info[:2]
    paths: list[Path] = []
    for prefix in prefixes:
        root = Path(prefix) / "lib"
        paths.extend(
            (
                root / f"python{major}.{minor}" / "dist-packages",
                root / f"python{major}" / "dist-packages",
            )
        )
    return tuple(dict.fromkeys(paths))


def available_apt_pkg_abis(paths: Iterable[Path]) -> tuple[str, ...]:
    """Return CPython ABI tags exposed by ``apt_pkg`` in distro paths."""
    pattern = re.compile(r"apt_pkg\.cpython-(\d+).*\.so$")
    abis: set[str] = set()
    for path in paths:
        if not path.is_dir():
            continue
        for extension in path.glob("apt_pkg.cpython-*.so"):
            match = pattern.match(extension.name)
            if match:
                abis.add(match.group(1))
    return tuple(sorted(abis))


def import_apt_modules() -> tuple[ModuleType, ModuleType]:
    """Import ``apt`` and ``apt_pkg``, trying compatible distro paths once."""
    try:
        return importlib.import_module("apt"), importlib.import_module("apt_pkg")
    except ImportError:
        pass

    paths = system_site_paths()
    for path in paths:
        path_text = str(path)
        if path.is_dir() and path_text not in sys.path:
            sys.path.append(path_text)

    importlib.invalidate_caches()
    try:
        return importlib.import_module("apt"), importlib.import_module("apt_pkg")
    except ImportError as error:
        expected_abi = f"{sys.version_info.major}{sys.version_info.minor}"
        available_abis = available_apt_pkg_abis(paths)
        if available_abis and expected_abi not in available_abis:
            available = ", ".join(f"CPython 3.{abi[1:]}" for abi in available_abis)
            raise AptUnavailableError(
                "Debian's python3-apt package is installed, but it provides "
                f"apt_pkg for {available}; kerntop is running CPython "
                f"{sys.version_info.major}.{sys.version_info.minor}. Use a "
                "virtual environment with one of the supported Python versions."
            ) from error
        raise AptUnavailableError(
            "kerntop needs Debian's python3-apt package, but its apt bindings "
            "could not be imported. Install python3-apt for this system Python "
            "and use a matching Python 3.12 environment."
        ) from error
