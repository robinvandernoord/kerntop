# kerntop

`kerntop` is a safe terminal user interface for managing Linux kernel packages
on Debian- and Ubuntu-based systems. It is designed for servers and SSH
sessions: no graphical desktop or graphical libraries are required.

It presents installed and repository-available kernels in an ncdu-style
browser, marks and protects the running kernel, and keeps kernel meta packages
out of package actions.

> [!WARNING]
> kerntop can run real `apt-get` transactions when started as root. From a
> read-only session, press `e` to restart through `sudo`. Read the confirmation
> dialog and preview a transaction before
> applying it.

## Install

### Quick start

Run the latest release without installing it permanently:

```console
$ uv tool run kerntop
$ uvenv run kerntop
$ pipx run kerntop
```

### Install with pip

Install from PyPI with Python 3.11 or newer:

```console
$ pip install kerntop
```

### System prerequisite

`kerntop` uses Debian's `python3-apt` bindings to read package state. Install
the distribution package if it is not already present:

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

From an unprivileged session, press `e` to restart kerntop through `sudo`.
The application closes before `sudo` prompts for your password, so the normal
terminal authentication flow works over local terminals and SSH sessions.

The same entry points are available as command line flags, which may be
combined (`kerntop -eu`):

- `-e`, `--elevate` restarts through `sudo` before the interface starts, so the
  session begins in root mode.
- `-u`, `--header-cleanup` opens the header cleanup review as soon as the apt
  cache has loaded.
- `-h`, `--help` starts the interface on its Help screen.

Use the arrow keys and Enter to browse kernel series and builds. Press `h` in
the application for the complete key reference. The primary actions are:

- `a` toggles the recommended and all-variants views.
- `p` previews the contextual install or removal with `apt-get --simulate` in
  root mode.
- `q` queues a contextual install or removal for one combined transaction in
  root mode.
- `c` reviews, simulates, applies, or clears queued package actions.
- `i` installs an available kernel image after confirmation in root mode.
- `d` removes an installed, non-running kernel image after confirmation in
  root mode.
- `u` reviews unused versioned development headers and kernel-support packages
  from the main browser.
- `e` restarts kerntop with `sudo` from a read-only session.
- `r` refreshes repository indexes and reloads the cache in root mode; it only
  reloads the local cache in a read-only session.

## Safety model

- The currently running kernel cannot be selected for removal or purge.
- The browser warns when no non-running fallback kernel is installed, and
  repeats that warning before removing the final fallback.
- Kernel meta packages are protected and are never package-action targets.
- Package changes require root; unprivileged sessions are read-only.
- Queued changes can be simulated before their final confirmation.
- Removal and purge actions require explicit confirmation.
- Header and kernel-support cleanup lists explicit packages and never runs
  `autoremove` automatically.

## Scope and current limitations

kerntop supports apt-based Debian- and Ubuntu-based systems. It deliberately
has a narrow scope:

- It requires the distribution-provided `python3-apt` binding.
- The available-kernel view comes from the local apt cache. Refresh repository
  indexes with `r` in root mode when that cache is stale.
- Recommended variants follow the running kernel's flavour. We deliberately do
  not use installed meta-package dependencies because they only select their
  current targets and can hide other available kernels of the same flavour.
- Kernel installation targets image packages. Headers and kernel-support
  packages are handled through their separate cleanup workflow.
- Package previews, queues, and changes require root mode.
- It never runs `autoremove` automatically.
