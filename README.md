# kerntop

`kerntop` is a terminal user interface for inspecting and managing Linux kernel
packages on Debian- and Ubuntu-based systems. It is designed for servers and
SSH sessions: no graphical desktop or graphical libraries are required.

It presents installed and repository-available kernels in an ncdu-style
browser, marks the running kernel, and keeps kernel meta packages out of
package actions.

> [!WARNING]
> `kerntop` 0.0.7 is an early release. It can run real `apt-get` transactions
> when started as root. Read the confirmation dialog and preview a transaction
> before applying it.

## Install

### Quick start

Run the latest release without installing it permanently:

```console
$ uv tool run kerntop
$ uvenv run kerntop
$ pipx run kerntop
```

### Install with pip

Install from PyPI with Python 3.12 or newer:

```console
$ pip install kerntop
```

`kerntop` uses Debian's `python3-apt` bindings to read package state. Install
that distribution package if it is not already present:

```console
$ sudo apt-get install python3-apt
```

On systems where `pip` installs into a virtual environment, kerntop locates
supported system site-package directories so it can use the distribution's
`python-apt` binding. If the binding cannot be loaded, kerntop reports the
problem rather than falling back to parsing apt command output.

## Usage

Start in read-only mode:

```console
$ kerntop
```

Start with package-action controls enabled:

```console
$ sudo kerntop
```

Use the arrow keys and Enter to browse kernel series and builds. Press `h` in
the application for the complete key reference. The primary actions are:

- `a` toggles the recommended and all-variants views.
- `p` previews the contextual install or removal with `apt-get --simulate`.
- `q` queues a contextual install or removal for one combined transaction.
- `i` installs an available kernel image after confirmation.
- `d` removes an installed, non-running kernel image after confirmation.
- `u` reviews unused versioned headers and kernel-support packages.

## Safety model

- The currently running kernel cannot be selected for removal or purge.
- The browser warns when no non-running fallback kernel is installed, and
  repeats that warning before removing the final fallback.
- Kernel meta packages are protected and are never package-action targets.
- Package changes require root; unprivileged sessions are read-only.
- Queued changes can be simulated before their final confirmation.
- Header and kernel-support cleanup lists explicit packages and never runs
  `autoremove` automatically.

## Scope and current limitations

The local apt cache supplies the available-kernel view; 0.0.7 does not refresh
repository indexes itself. Kernel images are installed as image packages, while
headers and support packages are handled separately. See [PLAN.md](PLAN.md) for
the remaining MVP safety work.
