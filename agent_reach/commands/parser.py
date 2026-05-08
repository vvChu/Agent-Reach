"""Argument parser construction for the Agent Reach CLI."""

from __future__ import annotations

import argparse


def build_parser(version: str) -> argparse.ArgumentParser:
    """Build the top-level CLI parser."""
    parser = argparse.ArgumentParser(
        prog="agent-reach",
        description="Give your AI Agent eyes to see the entire internet",
    )
    parser.add_argument("-v", "--verbose", action="store_true", help="Show debug logs")
    parser.add_argument("--version", action="version", version=f"Agent Reach v{version}")
    sub = parser.add_subparsers(dest="command", help="Available commands")

    sub.add_parser("setup", help="Interactive configuration wizard")

    p_install = sub.add_parser("install", help="One-shot installer with flags")
    p_install.add_argument(
        "--env",
        choices=["local", "server", "auto"],
        default="auto",
        help="Environment: local, server, or auto-detect",
    )
    p_install.add_argument(
        "--proxy",
        default="",
        help="Residential proxy for Reddit/Bilibili (http://user:pass@ip:port)",
    )
    p_install.add_argument(
        "--safe",
        action="store_true",
        help="Safe mode: skip automatic system changes, show what's needed instead",
    )
    p_install.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making any changes",
    )
    p_install.add_argument(
        "--channels",
        default="",
        help=(
            "Comma-separated optional channels to install "
            "(twitter,weibo,wechat,xiaoyuzhou,xueqiu,xiaohongshu,"
            "reddit,bilibili,douyin,linkedin,all)"
        ),
    )

    p_conf = sub.add_parser("configure", help="Set a config value or auto-extract from browser")
    p_conf.add_argument(
        "key",
        nargs="?",
        default=None,
        choices=[
            "proxy",
            "github-token",
            "groq-key",
            "twitter-cookies",
            "youtube-cookies",
            "xhs-cookies",
        ],
        help="What to configure (omit if using --from-browser)",
    )
    p_conf.add_argument("value", nargs="*", help="The value(s) to set")
    p_conf.add_argument(
        "--from-browser",
        metavar="BROWSER",
        choices=["chrome", "firefox", "edge", "brave", "opera"],
        help="Auto-extract ALL platform cookies from browser (chrome/firefox/edge/brave/opera)",
    )

    sub.add_parser("doctor", help="Check platform availability")

    p_uninstall = sub.add_parser(
        "uninstall",
        help="Remove all Agent Reach config, tokens, and skill files",
    )
    p_uninstall.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be removed without making any changes",
    )
    p_uninstall.add_argument(
        "--keep-config",
        action="store_true",
        help="Remove skill files only, keep ~/.agent-reach/ config and tokens",
    )

    p_skill = sub.add_parser("skill", help="Manage agent skill registration")
    p_skill_group = p_skill.add_mutually_exclusive_group(required=True)
    p_skill_group.add_argument(
        "--install",
        action="store_true",
        help="Install SKILL.md to agent skill directories",
    )
    p_skill_group.add_argument(
        "--uninstall",
        action="store_true",
        help="Remove SKILL.md from agent skill directories",
    )

    p_format = sub.add_parser("format", help="Clean and format platform API output")
    p_format.add_argument("platform", choices=["xhs"], help="Platform to format (xhs)")

    sub.add_parser("check-update", help="Check for new versions and changes")
    sub.add_parser("watch", help="Quick health check + update check (for scheduled tasks)")
    sub.add_parser("version", help="Show version")

    return parser
