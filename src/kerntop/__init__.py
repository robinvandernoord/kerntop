"""kerntop: a terminal interface for managing apt-based Linux kernels."""

import os
import sys
import typing as t

from .app import KerntopApp

USAGE = (
    "usage: kerntop [-e] [-u] [-h]\n"
    "  -e, --elevate         restart through sudo before starting the interface\n"
    "  -u, --header-cleanup  open the header cleanup review once the cache loads\n"
    "  -h, --help            start the interface on its help screen\n"
)

_FLAG_ALIASES = {
    "-e": "elevate",
    "--elevate": "elevate",
    "-u": "header-cleanup",
    "--header-cleanup": "header-cleanup",
    "-h": "help",
    "--help": "help",
}


class UsageError(ValueError):
    """Raised when the command line contains an unsupported argument."""


def parse_arguments(argv: t.Sequence[str]) -> set[str]:
    """Return the set of enabled options for the given command line arguments."""
    options: set[str] = set()
    for argument in argv:
        candidates = (
            [f"-{letter}" for letter in argument[1:]]
            if len(argument) > 2 and argument[0] == "-" and argument[1] != "-"
            else [argument]
        )
        for candidate in candidates:
            try:
                options.add(_FLAG_ALIASES[candidate])
            except KeyError:
                raise UsageError(f"unrecognised argument: {argument}") from None
    return options


def elevate(argv: t.Sequence[str]) -> None:
    """Replace this process with a sudo-wrapped kerntop carrying the same arguments."""
    os.execvp("sudo", ("sudo", "--", sys.executable, "-m", "kerntop", *argv))


def main() -> None:
    """Run the kerntop terminal interface."""
    argv = sys.argv[1:]
    try:
        options = parse_arguments(argv)
    except UsageError as error:
        sys.stderr.write(f"kerntop: {error}\n{USAGE}")
        raise SystemExit(2) from None
    if "elevate" in options and os.geteuid() != 0:
        try:
            elevate(argv)
        except OSError as error:
            sys.stderr.write(
                f"kerntop: unable to restart through sudo ({error}); "
                "starting in read-only mode.\n"
            )
    app = KerntopApp(
        show_help_on_start="help" in options,
        show_header_cleanup_on_start="header-cleanup" in options,
    )
    app.run()
    if app.elevate_on_exit:
        elevate(argv)
