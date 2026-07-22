"""kerntop: a terminal interface for managing apt-based Linux kernels."""

from .app import KerntopApp


def main() -> None:
    """Run the kerntop terminal interface."""
    KerntopApp().run()
