"""Reusable helpers for checking and installing CLI dependencies."""

from __future__ import annotations

import os
import shutil
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class BinaryDependency:
    """A dependency identified by one or more binaries on PATH."""

    label: str
    binaries: tuple[str, ...]
    install_hint: str

    def is_installed(self) -> bool:
        """Return whether any expected binary is available."""
        return any(shutil.which(binary) for binary in self.binaries)


@dataclass(frozen=True)
class InstallerOption:
    """A single installer command guarded by the presence of a tool."""

    tool: str
    command: tuple[str, ...]


def print_safe_dependency_report(dependencies: Iterable[BinaryDependency]) -> list[BinaryDependency]:
    """Print current dependency status and return any missing dependencies."""
    missing: list[BinaryDependency] = []
    for dependency in dependencies:
        if dependency.is_installed():
            print(f"  ✅ {dependency.label} already installed")
        else:
            print(f"  -- {dependency.label} not found")
            missing.append(dependency)
    return missing


def print_dry_run_dependency_report(
    dependencies: Iterable[BinaryDependency],
    *,
    install_prefix: str = "would install via:",
) -> None:
    """Print dry-run dependency status for each dependency."""
    for dependency in dependencies:
        if dependency.is_installed():
            print(f"  ✅ {dependency.label}: already installed, skip")
        else:
            print(f"  {dependency.label}: {install_prefix} {dependency.install_hint}")


def install_with_fallbacks(
    *,
    label: str,
    success_binary: str,
    installer_options: Sequence[InstallerOption],
    already_installed_message: str,
    success_message: str,
    failure_message: str,
) -> None:
    """Install a tool using the first available package manager fallback."""
    print(f"Setting up {label}...")
    if shutil.which(success_binary):
        print(already_installed_message)
        return

    for option in installer_options:
        if not shutil.which(option.tool):
            continue
        try:
            subprocess.run(
                list(option.command),
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except Exception:
            continue
        if shutil.which(success_binary):
            print(success_message)
            return

    print(failure_message)


def npm_global_package_installed(package_name: str) -> bool:
    """Return whether an npm global package directory appears to be installed."""
    npm_cmd = shutil.which("npm")
    if not npm_cmd:
        return False
    try:
        npm_root = subprocess.run(
            [npm_cmd, "root", "-g"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        ).stdout.strip()
    except Exception:
        return False
    if not npm_root:
        return False
    return os.path.isdir(os.path.join(npm_root, package_name))
