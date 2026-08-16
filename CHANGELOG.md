# Changelog

<!-- next-version-placeholder -->

## v0.2.0 (2026-08-16)

### Features
* cli flags to start in specific modes (-e, -u)
* make `r` in sudo-mode also apt-update before reloading local cache
* **apt:** support safe interruption and header installs
* `:q` to quit easter egg
* Support 'e' to elevant to sudo

### Fixes
* **kernels:** sort version series numerically
* **kernels:** restore flavour-based discovery
* kerntop --help now launches the TUI directly into its existing Help screen.
* **app:** display installed package version in help
* **kernels:** select recommended images from meta packages
* **kernels:** support unsigned Ubuntu image packages
* minor UI tweaks
* show extra warning when last fallback kernel is about to be removed via queue
* support Python 3.11
* **kernels:** warn before final fallback removal
* **kernels:** detect flavours after ABI revisions

## 0.1.2 (2026-07-24)

### Fixes

- Recommended kernel images consistently follow the running kernel's flavour.
- Kernel series are sorted numerically by major and minor version.

## 0.1.1 (2026-07-24)

### Fixes

- `kerntop --help` now opens the in-app Help screen directly.
- The Help screen displays the installed package version.
- Recommended kernel images follow installed kernel image meta-package
  dependencies when available, including unsigned Ubuntu image variants.

## 0.1.0 (2026-07-24)

### Features

- Added a safe terminal interface for reviewing, installing, and removing
  kernels on apt-based systems.
- Added package previews, queued actions, kernel safety checks, and explicit
  cleanup for unused headers and kernel-support packages.
