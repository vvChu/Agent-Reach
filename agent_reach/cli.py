# -*- coding: utf-8 -*-
"""
Agent Reach CLI — installer, doctor, and configuration tool.

Usage:
    agent-reach install --env=auto
    agent-reach doctor
    agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy"
    agent-reach setup
"""

from __future__ import annotations

import os
import sys
import time

from agent_reach import __version__
from agent_reach.commands import dispatch_command
from agent_reach.commands.configure import (
    configure_xhs_cookies as _configure_xhs_cookies_impl,
)
from agent_reach.commands.configure import (
    parse_twitter_cookie_input as _parse_twitter_cookie_input_impl,
)
from agent_reach.commands.configure import run_configure
from agent_reach.commands.formatting import run_format_command
from agent_reach.commands.install import InstallHooks, run_install
from agent_reach.commands.install import detect_environment as _detect_environment_impl
from agent_reach.commands.install import install_bili_deps as _install_bili_deps_impl
from agent_reach.commands.install import install_mcporter as _install_mcporter_impl
from agent_reach.commands.install import install_mcporter_safe as _install_mcporter_safe_impl
from agent_reach.commands.install import install_reddit_deps as _install_reddit_deps_impl
from agent_reach.commands.install import install_system_deps as _install_system_deps_impl
from agent_reach.commands.install import (
    install_system_deps_dryrun as _install_system_deps_dryrun_impl,
)
from agent_reach.commands.install import install_system_deps_safe as _install_system_deps_safe_impl
from agent_reach.commands.install import install_twitter_deps as _install_twitter_deps_impl
from agent_reach.commands.install import install_wechat_deps as _install_wechat_deps_impl
from agent_reach.commands.install import install_weibo_deps as _install_weibo_deps_impl
from agent_reach.commands.install import install_xhs_deps as _install_xhs_deps_impl
from agent_reach.commands.install import install_xiaoyuzhou_deps as _install_xiaoyuzhou_deps_impl
from agent_reach.commands.maintenance import (
    classify_github_response_error as _classify_github_response_error_impl,
)
from agent_reach.commands.maintenance import classify_update_error as _classify_update_error_impl
from agent_reach.commands.maintenance import github_get_with_retry as _github_get_with_retry_impl
from agent_reach.commands.maintenance import (
    run_check_update,
    run_doctor,
    run_setup,
    run_uninstall,
    run_watch,
)
from agent_reach.commands.maintenance import update_error_text as _update_error_text_impl
from agent_reach.commands.parser import build_parser
from agent_reach.commands.skill import install_skill as _install_skill_impl
from agent_reach.commands.skill import run_skill_command
from agent_reach.commands.skill import uninstall_skill as _uninstall_skill_impl


def _ensure_utf8_console() -> None:
    """Best-effort Windows console UTF-8 setup for CLI runtime only."""
    if sys.platform != "win32":
        return
    if os.environ.get("PYTEST_CURRENT_TEST"):
        return
    try:
        import io

        if hasattr(sys.stdout, "buffer"):
            sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "buffer"):
            sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    except Exception:
        pass


def _configure_logging(verbose: bool = False) -> None:
    """Suppress loguru output unless --verbose is set."""
    from loguru import logger

    logger.remove()
    if verbose:
        logger.add(sys.stderr, level="INFO")


def main() -> None:
    _ensure_utf8_console()

    parser = build_parser(__version__)
    args = parser.parse_args()

    _configure_logging(getattr(args, "verbose", False))

    if not args.command:
        parser.print_help()
        sys.exit(0)

    if args.command == "version":
        print(f"Agent Reach v{__version__}")
        sys.exit(0)

    handlers = {
        "doctor": lambda _args: _cmd_doctor(),
        "check-update": lambda _args: _cmd_check_update(),
        "watch": lambda _args: _cmd_watch(),
        "setup": lambda _args: _cmd_setup(),
        "install": _cmd_install,
        "configure": _cmd_configure,
        "uninstall": _cmd_uninstall,
        "skill": _cmd_skill,
        "format": _cmd_format,
    }
    dispatch_command(args, handlers)


def _load_browser_cookie_configurer():
    from agent_reach.cookie_extract import configure_from_browser

    return configure_from_browser


def _configure_from_browser(browser, config):
    return _load_browser_cookie_configurer()(browser, config)


def _check_all(config):
    from agent_reach.doctor import check_all

    return check_all(config)


def _format_doctor_report(results):
    from agent_reach.doctor import format_report

    return format_report(results)


def _build_install_hooks() -> InstallHooks:
    return InstallHooks(
        detect_environment=_detect_environment,
        install_system_deps=_install_system_deps,
        install_system_deps_safe=_install_system_deps_safe,
        install_system_deps_dryrun=_install_system_deps_dryrun,
        install_mcporter=_install_mcporter,
        install_mcporter_safe=_install_mcporter_safe,
        channel_installers={
            "twitter": _install_twitter_deps,
            "weibo": _install_weibo_deps,
            "wechat": _install_wechat_deps,
            "xiaoyuzhou": _install_xiaoyuzhou_deps,
            "xiaohongshu": _install_xhs_deps,
            "reddit": _install_reddit_deps,
            "bilibili": _install_bili_deps,
        },
        cookie_channels={"twitter", "xueqiu", "bilibili"},
        install_skill=_install_skill,
        configure_from_browser=_configure_from_browser,
        check_all=_check_all,
        format_report=_format_doctor_report,
    )


def _cmd_install(args):
    run_install(args, _build_install_hooks())


def _install_system_deps():
    _install_system_deps_impl()


def _install_xiaoyuzhou_deps():
    _install_xiaoyuzhou_deps_impl()


def _install_twitter_deps():
    _install_twitter_deps_impl()


def _install_xhs_deps():
    _install_xhs_deps_impl()


def _install_reddit_deps():
    _install_reddit_deps_impl()


def _install_bili_deps():
    _install_bili_deps_impl()


def _install_weibo_deps():
    _install_weibo_deps_impl()


def _install_wechat_deps():
    _install_wechat_deps_impl()


def _install_system_deps_safe():
    _install_system_deps_safe_impl()


def _install_system_deps_dryrun():
    _install_system_deps_dryrun_impl()


def _install_mcporter():
    _install_mcporter_impl()


def _install_mcporter_safe():
    _install_mcporter_safe_impl()


def _detect_environment():
    return _detect_environment_impl()


def _install_skill():
    _install_skill_impl(expanduser=os.path.expanduser, environ=os.environ)


def _uninstall_skill():
    _uninstall_skill_impl(expanduser=os.path.expanduser, environ=os.environ)


def _cmd_skill(args):
    run_skill_command(args, install=_install_skill, uninstall=_uninstall_skill)


def _cmd_format(args):
    run_format_command(args)


def _cmd_configure(args):
    run_configure(args, browser_configurer=_configure_from_browser)


def _parse_twitter_cookie_input(value: str):
    return _parse_twitter_cookie_input_impl(value)


def _configure_xhs_cookies(value):
    return _configure_xhs_cookies_impl(value, expanduser=os.path.expanduser)


def _cmd_uninstall(args):
    run_uninstall(args, expanduser=os.path.expanduser)


def _cmd_doctor():
    run_doctor(
        check_all_fn=_check_all,
        format_report_fn=_format_doctor_report,
        install_skill=_install_skill,
    )


def _cmd_setup():
    run_setup()


def _classify_update_error(exc):
    return _classify_update_error_impl(exc)


def _update_error_text(kind):
    return _update_error_text_impl(kind)


def _classify_github_response_error(resp):
    return _classify_github_response_error_impl(resp)


def _github_get_with_retry(url, timeout=10, retries=3, sleeper=time.sleep):
    return _github_get_with_retry_impl(url, timeout=timeout, retries=retries, sleeper=sleeper)


def _cmd_check_update():
    return run_check_update(__version__, getter=_github_get_with_retry)


def _cmd_watch():
    return run_watch(__version__, check_all_fn=_check_all, getter=_github_get_with_retry)
