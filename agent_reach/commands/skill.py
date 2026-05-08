"""Skill installation and removal commands."""

from __future__ import annotations

import argparse
import importlib.resources
import os
import shutil
from pathlib import Path
from typing import Any


def _is_english_locale(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized.startswith("en") or normalized.startswith("english")


def _skill_resource_name(environ: dict[str, str] | os._Environ[str]) -> str:
    locale_candidates = (
        environ.get("AGENT_REACH_LANG", ""),
        environ.get("LC_ALL", ""),
        environ.get("LC_MESSAGES", ""),
        environ.get("LANG", ""),
    )
    if any(_is_english_locale(candidate) for candidate in locale_candidates):
        return "SKILL_en.md"
    return "SKILL.md"


def _read_skill_markdown(skill_pkg: Any, environ: dict[str, str] | os._Environ[str]) -> str:
    resource_name = _skill_resource_name(environ)
    try:
        return skill_pkg.joinpath(resource_name).read_text(encoding="utf-8")
    except FileNotFoundError:
        return skill_pkg.joinpath("SKILL.md").read_text(encoding="utf-8")


def _copy_skill_dir(
    target: str,
    *,
    environ: dict[str, str] | os._Environ[str],
) -> bool:
    """Copy the packaged skill directory to a target location."""
    try:
        if os.path.exists(target):
            shutil.rmtree(target)
        os.makedirs(target, exist_ok=True)

        try:
            skill_pkg = importlib.resources.files("agent_reach").joinpath("skill")
            skill_md = _read_skill_markdown(skill_pkg, environ)
        except Exception:
            skill_pkg = Path(__file__).resolve().parents[1] / "skill"
            skill_md = _read_skill_markdown(skill_pkg, environ)

        with open(os.path.join(target, "SKILL.md"), "w", encoding="utf-8") as handle:
            handle.write(skill_md)

        refs_pkg = skill_pkg.joinpath("references")
        refs_target = os.path.join(target, "references")
        os.makedirs(refs_target, exist_ok=True)

        for ref_file in refs_pkg.iterdir():
            name = ref_file.name if hasattr(ref_file, "name") else str(ref_file).split("/")[-1]
            if name.endswith(".md"):
                content = (
                    ref_file.read_text(encoding="utf-8")
                    if hasattr(ref_file, "read_text")
                    else ref_file.read_text()
                )
                with open(os.path.join(refs_target, name), "w", encoding="utf-8") as handle:
                    handle.write(content)

        return True
    except Exception as exc:
        print(f"  Warning: Could not install skill: {exc}")
        return False


def install_skill(
    *,
    expanduser=os.path.expanduser,
    environ: dict[str, str] | os._Environ[str] | None = None,
) -> None:
    """Install Agent Reach as an agent skill."""
    env = environ or os.environ
    skill_dirs = [
        expanduser("~/.agents/skills"),
        expanduser("~/.openclaw/skills"),
        expanduser("~/.claude/skills"),
    ]

    openclaw_home = env.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(0, os.path.join(openclaw_home, ".openclaw", "skills"))

    installed = False
    for skill_dir in skill_dirs:
        if os.path.isdir(skill_dir):
            target = os.path.join(skill_dir, "agent-reach")
            if _copy_skill_dir(target, environ=env):
                platform_name = (
                    "Agent"
                    if ".agents" in skill_dir
                    else "OpenClaw"
                    if "openclaw" in skill_dir
                    else "Claude Code"
                )
                print(f"Skill installed for {platform_name}: {target}")
                installed = True

    if not installed:
        target = expanduser("~/.agents/skills/agent-reach")
        os.makedirs(os.path.dirname(target), exist_ok=True)
        if _copy_skill_dir(target, environ=env):
            print(f"Skill installed: {target}")
        else:
            print("  -- Could not install agent skill (optional)")
            print("  -- Tip: install OpenClaw, Claude Code, or create ~/.agents/skills/ manually")


def uninstall_skill(
    *,
    expanduser=os.path.expanduser,
    environ: dict[str, str] | os._Environ[str] | None = None,
) -> None:
    """Remove Agent Reach from known agent skill directories."""
    env = environ or os.environ
    skill_dirs = [
        ("~/.openclaw/skills/agent-reach", "OpenClaw"),
        ("~/.claude/skills/agent-reach", "Claude Code"),
        ("~/.agents/skills/agent-reach", "Agent"),
    ]

    openclaw_home = env.get("OPENCLAW_HOME")
    if openclaw_home:
        skill_dirs.insert(
            0,
            (os.path.join(openclaw_home, ".openclaw", "skills", "agent-reach"), "OpenClaw"),
        )

    removed = False
    for skill_path_template, platform_name in skill_dirs:
        skill_path = expanduser(skill_path_template)
        if os.path.isdir(skill_path):
            try:
                shutil.rmtree(skill_path)
                print(f"  Removed {platform_name} skill: {skill_path}")
                removed = True
            except Exception as exc:
                print(f"  Could not remove {skill_path}: {exc}")

    if not removed:
        print("  No skill installations found.")


def run_skill_command(
    args: argparse.Namespace,
    *,
    install=install_skill,
    uninstall=uninstall_skill,
) -> None:
    """Dispatch the `agent-reach skill` subcommands."""
    if args.install:
        install()
    elif args.uninstall:
        uninstall()
