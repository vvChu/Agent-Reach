"""Maintenance and diagnostics CLI commands."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import time
from collections.abc import Callable
from typing import Any

# Error-message fragments used to classify DNS failures across requests/urllib3
# variants on different platforms.
from agent_reach.config import Config
from agent_reach.doctor import check_all, format_report

DNS_ERROR_MARKERS = (
    "name or service not known",
    "temporary failure in name resolution",
    "nodename nor servname",
    "getaddrinfo failed",
    "name resolution",
    "dns",
)


def _is_dns_error_message(message: str) -> bool:
    """Return True when a connection error message indicates DNS resolution failure."""
    return any(marker in message for marker in DNS_ERROR_MARKERS)


def _load_rich_printer() -> Callable[..., None]:
    try:
        from rich import print as rich_print

        return rich_print
    except ImportError:
        return print


def run_doctor(
    *,
    config_factory=Config,
    check_all_fn=check_all,
    format_report_fn=format_report,
    install_skill: Callable[[], None] | None = None,
    rich_printer_loader: Callable[[], Callable[..., None]] = _load_rich_printer,
) -> None:
    """Run doctor checks and print a formatted report."""
    printer = rich_printer_loader()
    config = config_factory()
    results = check_all_fn(config)
    printer(format_report_fn(results))

    if install_skill is not None:
        install_skill()


def run_setup(
    *,
    config_factory=Config,
    which=shutil.which,
    run_subprocess=subprocess.run,
    input_fn=input,
) -> None:
    """Run the interactive setup wizard."""
    config = config_factory()
    print()
    print("Agent Reach Setup")
    print("=" * 40)
    print()

    print("【推荐】全网搜索 — Exa（通过 mcporter）")
    print("  免费，无需 API Key")

    if not which("mcporter"):
        print("  当前状态: -- mcporter 未安装")
        print("  安装：npm install -g mcporter")
        print("  然后：mcporter config add exa https://mcp.exa.ai/mcp")
        print()
    else:
        try:
            result = run_subprocess(
                ["mcporter", "config", "list"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            if "exa" in result.stdout.lower():
                print("  当前状态: ✅ 已配置")
            else:
                print("  当前状态: -- 未配置")
                setup_now = input_fn("  现在自动配置 Exa 吗？[Y/n]: ").strip().lower()
                if setup_now in ("", "y", "yes"):
                    add_result = run_subprocess(
                        ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=10,
                    )
                    if add_result.returncode == 0:
                        print("  ✅ Exa 已配置")
                    else:
                        print("  [!] 自动配置失败，请手动执行：")
                        print("     mcporter config add exa https://mcp.exa.ai/mcp")
        except Exception:
            print("  [!] 无法检查 Exa 配置，请手动执行：")
            print("     mcporter config add exa https://mcp.exa.ai/mcp")
        print()

    print("【可选】GitHub Token — 提高 API 限额")
    print("  无 token: 60 次/小时 | 有 token: 5000 次/小时")
    print("  获取: https://github.com/settings/tokens (无需任何权限)")
    current = config.get("github_token")
    if current:
        print("  当前状态: ✅ 已配置")
    else:
        key = input_fn("  GITHUB_TOKEN (回车跳过): ").strip()
        if key:
            config.set("github_token", key)
            print("  ✅ GitHub API 已提升至 5000 次/小时！")
        else:
            print("  跳过。公开 API 也能用")
    print()

    print("【信息】Reddit — 通过 rdt-cli 搜索和阅读，无需配置")
    print("  安装：pipx install rdt-cli")
    print()

    print("【可选】Groq API — 视频无字幕时的语音转文字")
    print("  免费额度，注册: https://console.groq.com")
    current = config.get("groq_api_key")
    if current:
        print("  当前状态: ✅ 已配置")
    else:
        key = input_fn("  GROQ_API_KEY (回车跳过): ").strip()
        if key:
            config.set("groq_api_key", key)
            print("  ✅ 语音转文字已开启！")
        else:
            print("  跳过")
    print()

    print("=" * 40)
    print(f"✅ 配置已保存到 {config.config_path}")
    print("运行 agent-reach doctor 查看完整状态")
    print()


def run_uninstall(
    args: argparse.Namespace,
    *,
    expanduser=os.path.expanduser,
    isdir=os.path.isdir,
    which=shutil.which,
    rmtree=shutil.rmtree,
    run_subprocess=subprocess.run,
) -> None:
    """Remove Agent Reach config, tokens, and skill files."""
    dry_run = bool(args.dry_run)
    keep_config = bool(args.keep_config)

    print()
    print("Agent Reach Uninstaller")
    print("=" * 40)

    if dry_run:
        print("DRY RUN — showing what would be removed (no changes)")
        print()

    removed_any = False
    config_dir = expanduser("~/.agent-reach")
    if not keep_config:
        if isdir(config_dir):
            if dry_run:
                print(f"[dry-run] Would remove config directory: {config_dir}")
                print("          (contains config.yaml with all tokens/cookies/API keys)")
            else:
                try:
                    rmtree(config_dir)
                    print(f"  Removed config directory: {config_dir}")
                    removed_any = True
                except Exception as exc:
                    print(f"  Could not remove {config_dir}: {exc}")
        else:
            print(f"  Config directory not found (already clean): {config_dir}")
    else:
        print(f"  Skipping config directory (--keep-config): {config_dir}")

    skill_dirs = [
        ("~/.openclaw/skills/agent-reach", "OpenClaw"),
        ("~/.claude/skills/agent-reach", "Claude Code"),
        ("~/.agents/skills/agent-reach", "Agent"),
    ]

    for skill_path_template, platform_name in skill_dirs:
        skill_path = expanduser(skill_path_template)
        if isdir(skill_path):
            if dry_run:
                print(f"[dry-run] Would remove {platform_name} skill: {skill_path}")
            else:
                try:
                    rmtree(skill_path)
                    print(f"  Removed {platform_name} skill: {skill_path}")
                    removed_any = True
                except Exception as exc:
                    print(f"  Could not remove {skill_path}: {exc}")

    if which("mcporter"):
        for mcp_name in ("exa", "xiaohongshu"):
            try:
                result = run_subprocess(
                    ["mcporter", "list"],
                    capture_output=True,
                    encoding="utf-8",
                    errors="replace",
                    timeout=10,
                )
                if mcp_name in result.stdout:
                    if dry_run:
                        print(f"[dry-run] Would remove mcporter entry: {mcp_name}")
                    else:
                        run_subprocess(
                            ["mcporter", "config", "remove", mcp_name],
                            capture_output=True,
                            encoding="utf-8",
                            errors="replace",
                            timeout=10,
                        )
                        print(f"  Removed mcporter entry: {mcp_name}")
                        removed_any = True
            except Exception:
                pass

    print()
    if dry_run:
        print("Dry run complete. No changes were made.")
        print("Run without --dry-run to actually remove the above.")
    else:
        if removed_any:
            print("Agent Reach data removed.")
        else:
            print("Nothing to remove — already clean.")

    print()
    print("Optional: remove the Agent Reach Python package itself:")
    print("  pip uninstall agent-reach")
    print()
    print("Optional: remove tools installed by Agent Reach:")
    print("  npm uninstall -g mcporter")
    print("  pipx uninstall twitter-cli")
    print("  npm uninstall -g undici")


def classify_update_error(exc: Exception) -> str:
    """Classify update-check exceptions for user-facing diagnostics."""
    import requests

    if isinstance(exc, requests.exceptions.Timeout):
        return "timeout"
    if isinstance(exc, requests.exceptions.ConnectionError):
        message = str(exc).lower()
        if _is_dns_error_message(message):
            return "dns"
        return "connection"
    if isinstance(exc, requests.exceptions.HTTPError):
        return "http"
    return "unknown"


def update_error_text(kind: str) -> str:
    """Map internal update-check error kinds to user-facing text."""
    mapping = {
        "timeout": "网络超时",
        "dns": "DNS 解析失败",
        "rate_limit": "GitHub API 速率限制",
        "connection": "网络连接失败",
        "server_error": "GitHub 服务暂时不可用",
        "http": "HTTP 请求失败",
        "unknown": "未知网络错误",
    }
    return mapping.get(kind, "请求失败")


def classify_github_response_error(resp: Any) -> str | None:
    """Classify non-200 GitHub responses that need special handling."""
    if resp is None:
        return "unknown"
    if resp.status_code == 429:
        return "rate_limit"
    if resp.status_code == 403:
        remaining = resp.headers.get("X-RateLimit-Remaining", "")
        if remaining == "0":
            return "rate_limit"
        try:
            message = resp.json().get("message", "").lower()
            if "rate limit" in message:
                return "rate_limit"
        except Exception:
            pass
    if 500 <= resp.status_code < 600:
        return "server_error"
    return None


def github_get_with_retry(
    url: str,
    timeout: int = 10,
    retries: int = 3,
    sleeper: Callable[[float], None] = time.sleep,
    requests_get: Callable[..., Any] | None = None,
) -> tuple[Any | None, str | None, int]:
    """GET a GitHub API endpoint with retry/backoff and error classification."""
    import requests

    getter = requests_get or requests.get
    for attempt in range(1, retries + 1):
        try:
            resp = getter(url, timeout=timeout)
        except requests.exceptions.RequestException as exc:
            if attempt >= retries:
                return None, classify_update_error(exc), attempt
            sleeper(2 ** (attempt - 1))
            continue

        err_kind = classify_github_response_error(resp)
        if err_kind in ("rate_limit", "server_error"):
            if attempt >= retries:
                return None, err_kind, attempt
            delay = 2 ** (attempt - 1)
            retry_after = resp.headers.get("Retry-After")
            if err_kind == "rate_limit" and retry_after:
                try:
                    delay = max(delay, float(retry_after))
                except Exception:
                    pass
            sleeper(delay)
            continue

        return resp, None, attempt

    return None, "unknown", retries


def run_check_update(
    current_version: str,
    *,
    getter: Callable[..., tuple[Any | None, str | None, int]] = github_get_with_retry,
) -> str:
    """Check GitHub for newer releases."""
    print(f"当前版本: v{current_version}")
    release_url = "https://api.github.com/repos/Panniantong/Agent-Reach/releases/latest"
    commit_url = "https://api.github.com/repos/Panniantong/Agent-Reach/commits/main"

    resp, err, attempts = getter(release_url, timeout=10, retries=3)
    if err:
        print(f"[!] 无法检查更新（{update_error_text(err)}，已重试 {attempts} 次）")
        return "error"

    if resp and resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        body = data.get("body", "")

        if latest and latest != current_version:
            print(f"最新版本: v{latest} ← 有更新！")
            if body:
                print()
                print("更新内容：")
                for line in body.strip().split("\n")[:20]:
                    print(f"  {line}")
            print()
            print("更新命令:")
            print("  pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")
            return "update_available"
        print("✅ 已是最新版本")
        return "up_to_date"

    release_err = classify_github_response_error(resp)
    if release_err == "rate_limit":
        print("[!] 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    resp2, err2, attempts2 = getter(commit_url, timeout=10, retries=2)
    if err2:
        print(f"[!] 无法检查更新（{update_error_text(err2)}，已重试 {attempts + attempts2} 次）")
        return "error"
    if resp2 and resp2.status_code == 200:
        commit = resp2.json()
        sha = commit.get("sha", "")[:7]
        message = commit.get("commit", {}).get("message", "").split("\n")[0]
        date = commit.get("commit", {}).get("committer", {}).get("date", "")[:10]
        print(f"最新提交: {sha} ({date}) {message}")
        print()
        print("更新命令:")
        print("  pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")
        return "unknown"

    commit_err = classify_github_response_error(resp2)
    if commit_err == "rate_limit":
        print("[!] 无法检查更新（GitHub API 速率限制，请稍后重试）")
        return "error"

    status_code = resp2.status_code if resp2 else "unknown"
    print(f"[!] 无法检查更新（GitHub 返回 {status_code}）")
    return "error"


def run_watch(
    current_version: str,
    *,
    config_factory=Config,
    check_all_fn=check_all,
    getter: Callable[..., tuple[Any | None, str | None, int]] = github_get_with_retry,
) -> None:
    """Run a concise health check suitable for cron/scheduled usage."""
    config = config_factory()
    issues: list[str] = []

    results = check_all_fn(config)
    ok = sum(1 for result in results.values() if result["status"] == "ok")
    total = len(results)

    for result in results.values():
        if result["status"] in ("off", "error"):
            issues.append(f"[X] {result['name']}：{result['message']}")
        elif result["status"] == "warn":
            issues.append(f"[!] {result['name']}：{result['message']}")

    update_available = False
    new_version = ""
    release_body = ""
    resp, err, _attempts = getter(
        "https://api.github.com/repos/Panniantong/Agent-Reach/releases/latest",
        timeout=10,
        retries=2,
    )
    if not err and resp and resp.status_code == 200:
        data = resp.json()
        latest = data.get("tag_name", "").lstrip("v")
        if latest and latest != current_version:
            update_available = True
            new_version = latest
            release_body = data.get("body", "")

    if not issues and not update_available:
        print(f"Agent Reach: 全部正常 ({ok}/{total} 渠道可用，v{current_version} 已是最新)")
        return

    print("Agent Reach 监控报告")
    print("=" * 40)
    print(f"版本: v{current_version}  |  渠道: {ok}/{total}")

    if issues:
        print()
        for issue in issues:
            print(f"  {issue}")

    if update_available:
        print()
        print(f"新版本可用: v{new_version}")
        if release_body:
            for line in release_body.strip().split("\n")[:10]:
                print(f"    {line}")
        print("  更新: pip install --upgrade https://github.com/Panniantong/agent-reach/archive/main.zip")
