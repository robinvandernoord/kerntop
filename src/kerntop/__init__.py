"""kerntop: a terminal interface for managing apt-based Linux kernels."""

import os
import sys

from .app import KerntopApp


def main() -> None:
    """Run the kerntop terminal interface."""
    app = KerntopApp(show_help_on_start="--help" in sys.argv[1:])
    app.run()
    if app.elevate_on_exit:
        os.execvp(
            "sudo",
            ("sudo", "--", sys.executable, "-m", "kerntop", *sys.argv[1:]),
        )
