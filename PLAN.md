Build an ncdu-like TUI (terminal user interface) for kernel management on apt-based Linux systems (Debian/Ubuntu servers, no GUI available).

Context: Linux Mint has a graphical "Kernel Manager" tool that clearly shows which kernels are installed, which are available, and lets you install/remove with a click. That tool doesn't exist on servers (no GUI). No direct TUI equivalent currently exists for this.

Name: kerntop

Stack:

Language: Python
TUI framework: Textual (Rich-based, own ANSI compositor, not curses-dependent) — with raw curses as an explicit fallback path if Textual proves unworkable for some reason
apt/dpkg integration:
Read-only state (installed kernel packages, candidate/available versions, version comparison) via python-apt (apt/apt_pkg modules) rather than parsing CLI text output
Actual install/remove transactions via subprocess calls to apt-get (native locking, progress reporting, interrupt-safety — don't reimplement this against libapt-pkg's transaction API)
Currently-running kernel resolved via uname -r, then mapped manually to its corresponding linux-image-<version> package name (no API shortcut for this mapping in any language)

Requirements:

Ncurses-style interface, navigable with arrow keys (like ncdu, aptitude)
Show in one view: installed kernel versions (linux-image/linux-headers packages), available versions in the repo, and which kernel is currently running
Clearly mark the currently running kernel so it's never accidentally removed (safety guard against an unbootable system)
Direct actions: install, remove/purge specific kernel versions, with confirmation
Works via apt/dpkg under the hood (no separate package manager)
Lightweight — no dependency on graphical libraries, pure terminal, works over SSH

Comparable existing tools for reference: aptitude (ncurses package manager, generic), APTUI (Go/Bubble Tea TUI for apt, generic package management, no kernel focus), purge-old-kernels (CLI script with no interface, from the byobu package).

Goal: a tool that specifically fills the kernel-management gap the generic tools leave open — the distinction between active/installed/available, and a safe removal workflow.

## Release 0.0.1: proof of concept

Validate the difficult integrations without making package changes to the host.

- Support Python 3.12+ and build the initial Textual interface for SSH use.
- Load native-architecture image packages and matching header information via
  `python-apt`; show installed packages, candidates from the local apt cache,
  and the running kernel in one navigable view.
- Resolve the running package manually from `uname -r` and never allow it to be
  selected for a removal preview.
- Make root state visible: a process launched under `sudo` exposes preview
  controls, while an unprivileged process remains read-only with a clear
  warning.
- Provide arrow-key navigation plus help, quit, and install/removal preview
  controls. Previews invoke `apt-get --simulate` only and render its output;
  no install, removal, purge, or `apt-get update` is executed in this release.
- Keep kernel meta packages protected and explain their purpose rather than
  making them selectable.
- Make PyPI installations compatible with distro-provided `python-apt` by
  locating supported system site-package paths; provide a clear diagnostic when
  the binding is unavailable instead of parsing apt CLI output.
- Add focused unit tests for pure package classification, running-kernel safety,
  compatibility-path lookup, and preview command construction.

Not included: real transaction confirmation/progress handling, repository
refresh, companion cleanup, fallback-kernel warnings, filtering/sorting, and
persistent settings.

## Release 0.1.0: minimum viable manager

Turn the proven interface into the safe manager described above.

- Replace the flat image list with an ncdu/Mint-Kernel-Manager-style hierarchy:
  first choose a kernel series (for example `6.9` or `7.0`) with installed and
  available counts, then drill into the builds and flavours in that series.
- Default the hierarchy to recommended images without hard-coding distribution
  flavour names: exclude packages marked as debug, prefer the flavour of the
  running kernel (such as PikaOS's `-pikaos`), and use relevant image meta
  package relationships where available. Provide an explicit all-variants view
  for unsigned, cloud, RT, debug, and other distribution-specific alternatives.
- Allow real `apt-get install`, `remove`, and `purge` only when the full program
  was launched under `sudo`; keep non-root sessions read-only.
- Support Mint-Kernel-Manager-style action queues: stage installations and
  removals, display the queued changes, then simulate and explicitly confirm
  the complete queue before applying it as one apt transaction.
- Simulate every transaction first, show its package plan, require an explicit
  final confirmation, stream actual `apt-get` progress, and interrupt child
  processes safely.
- Select versioned kernel image packages as the primary targets and include
  matching available headers for installation. Continue to protect meta
  packages.
- Add a privileged repository-refresh action using `apt-get update`, followed
  by a reload of the apt cache.
- Permanently block removal of the running kernel. Display a persistent warning
  when there is no non-running fallback image, and repeat the warning before
  removing the final fallback.
- After image removal, detect leftover matching headers/modules and offer an
  explicitly selected, separately simulated and confirmed cleanup action;
  never run autoremove automatically.
