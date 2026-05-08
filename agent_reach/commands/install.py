"""Install command implementation and environment helpers."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from agent_reach.config import Config
from agent_reach.dependencies import (
    BinaryDependency,
    InstallerOption,
    install_with_fallbacks,
    npm_global_package_installed,
    print_dry_run_dependency_report,
    print_safe_dependency_report,
)
from agent_reach.doctor import check_all, format_report

CookieResult = tuple[str, bool, str]
DoctorResults = dict[str, dict[str, Any]]


@dataclass(frozen=True)
class InstallHooks:
    """Injectable hooks for install command side effects.

    This keeps `run_install` testable by letting callers inject file-system,
    subprocess, doctor, and browser-cookie side effects while preserving the
    user-facing CLI flow.
    """

    detect_environment: Callable[[], str]
    install_system_deps: Callable[[], None]
    install_system_deps_safe: Callable[[], None]
    install_system_deps_dryrun: Callable[[], None]
    install_mcporter: Callable[[], None]
    install_mcporter_safe: Callable[[], None]
    channel_installers: Mapping[str, Callable[[], None]]
    cookie_channels: set[str]
    install_skill: Callable[[], None]
    configure_from_browser: Callable[[str, Config], list[CookieResult]]
    check_all: Callable[[Config], DoctorResults] = check_all
    format_report: Callable[[DoctorResults], str] = format_report
    config_factory: Callable[[], Config] = Config


SYSTEM_DEPENDENCIES = (
    BinaryDependency(
        label="GitHub CLI",
        binaries=("gh",),
        install_hint="https://cli.github.com — or: apt install gh / brew install gh",
    ),
    BinaryDependency(
        label="Node.js",
        binaries=("node", "npm"),
        install_hint="https://nodejs.org — or: apt install nodejs npm",
    ),
)


def run_install(args: Any, hooks: InstallHooks) -> None:
    """Execute the install command."""
    safe_mode = bool(args.safe)
    dry_run = bool(args.dry_run)

    config = hooks.config_factory()
    print()
    print("Agent Reach Installer")
    print("=" * 40)

    tools_dir = os.path.expanduser("~/.agent-reach/tools")
    os.makedirs(tools_dir, exist_ok=True)

    if dry_run:
        print("DRY RUN — showing what would be done (no changes)")
        print()
    if safe_mode:
        print("SAFE MODE — skipping automatic system changes")
        print()

    requested_channels = parse_requested_channels(args.channels, hooks.channel_installers)
    env = args.env if args.env != "auto" else hooks.detect_environment()

    if env == "server":
        print("Environment: Server/VPS (auto-detected)")
    else:
        print("Environment: Local computer (auto-detected)")

    if args.proxy:
        if dry_run:
            print("[dry-run] Would configure proxy for Bilibili")
        else:
            config.set("bilibili_proxy", args.proxy)
            print("✅ Proxy configured for Bilibili")

    print()
    if dry_run:
        hooks.install_system_deps_dryrun()
    elif safe_mode:
        hooks.install_system_deps_safe()
    else:
        hooks.install_system_deps()

    print()
    if dry_run:
        print("[dry-run] Would install mcporter and configure Exa search")
    elif safe_mode:
        hooks.install_mcporter_safe()
    else:
        hooks.install_mcporter()

    if requested_channels and not dry_run and not safe_mode:
        print()
        print("Installing optional channels...")
        for channel_name in sorted(requested_channels):
            installer = hooks.channel_installers.get(channel_name)
            if installer:
                installer()

    if requested_channels and dry_run:
        print()
        print(f"[dry-run] Would install optional channels: {', '.join(sorted(requested_channels))}")

    maybe_import_cookies(
        config=config,
        env=env,
        requested_channels=requested_channels,
        safe_mode=safe_mode,
        dry_run=dry_run,
        hooks=hooks,
    )

    if env == "server":
        print()
        print("Tip: Bilibili may block server IPs.")
        print("   Reddit: rdt-cli works without proxy (pipx install rdt-cli).")
        print("   For Bilibili full access: agent-reach configure proxy http://user:pass@ip:port")
        print("   Cheap option: https://www.webshare.io ($1/month)")

    if dry_run:
        print()
        print("Dry run complete. No changes were made.")
        return

    print()
    print("Testing channels...")
    results = hooks.check_all(config)
    ok = sum(1 for result in results.values() if result["status"] == "ok")
    total = len(results)

    print()
    print(hooks.format_report(results))
    print()

    hooks.install_skill()

    print(f"✅ Installation complete! {ok}/{total} channels active.")

    if not requested_channels:
        print()
        print("More channels available! Use --channels to install:")
        print("   agent-reach install --channels=twitter,weibo,xiaohongshu,...")
        print("   agent-reach install --channels=all  (install everything)")

    print()
    print("如果 Agent Reach 帮到了你，给个 Star 让更多人发现它吧：")
    print("   https://github.com/Panniantong/Agent-Reach")
    print("   只需一秒，对独立开发者意义很大。谢谢！")


def parse_requested_channels(
    raw_channels: str,
    channel_installers: Mapping[str, Callable[[], None]],
) -> set[str]:
    """Parse the optional --channels argument."""
    if not raw_channels:
        return set()

    raw = [channel.strip().lower() for channel in raw_channels.split(",") if channel.strip()]
    if "all" in raw:
        return set(channel_installers.keys()) | {"xueqiu", "douyin", "linkedin"}
    return set(raw)


def maybe_import_cookies(
    *,
    config: Config,
    env: str,
    requested_channels: set[str],
    safe_mode: bool,
    dry_run: bool,
    hooks: InstallHooks,
) -> None:
    """Import cookies when requested channels need them."""
    needs_cookies = bool(requested_channels & hooks.cookie_channels)
    if env == "local" and needs_cookies and not safe_mode and not dry_run:
        print()
        print("Importing cookies from browser...")
        print("  (macOS may ask for your login password to access the Keychain — this is normal,")
        print("   it only happens once during install. Enter your password or click 'Allow'.)")
        try:
            for browser in ("chrome", "firefox"):
                results = hooks.configure_from_browser(browser, config)
                if _print_cookie_results(results):
                    return
            print("  -- No cookies found (normal if you haven't logged into these sites)")
        except Exception:
            print("  -- Could not read browser cookies (browser might be open or password was denied)")
    elif env == "local" and needs_cookies and dry_run:
        print()
        print("[dry-run] Would try to import cookies from Chrome/Firefox")


def _print_cookie_results(results: list[CookieResult]) -> bool:
    found = False
    for platform_name, success, message in results:
        if success:
            print(f"  ✅ {platform_name}: {message}")
            found = True
    return found


def install_system_deps() -> None:
    """Install system-level dependencies: gh CLI, Node.js (for mcporter)."""
    print("Checking system dependencies...")
    _install_gh_cli()
    _install_nodejs()
    _install_undici()
    _configure_ytdlp_runtime()


def install_system_deps_safe() -> None:
    """Safe mode: check what's installed and print instructions for missing items."""
    print("Checking system dependencies (safe mode — no auto-install)...")
    missing = print_safe_dependency_report(SYSTEM_DEPENDENCIES)
    if missing:
        print()
        print("  To install missing dependencies manually:")
        for dependency in missing:
            print(f"    {dependency.label}: {dependency.install_hint}")
    else:
        print("  All system dependencies are installed!")


def install_system_deps_dryrun() -> None:
    """Dry-run: show what would be checked or installed."""
    print("[dry-run] System dependency check:")
    dry_run_dependencies = (
        BinaryDependency("gh CLI", ("gh",), "apt install gh / brew install gh"),
        BinaryDependency("Node.js", ("node",), "curl NodeSource setup | bash + apt install nodejs"),
    )
    print_dry_run_dependency_report(dry_run_dependencies)


def install_mcporter() -> None:
    """Install mcporter and configure Exa search."""
    print("Setting up mcporter (search backend)...")

    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
    else:
        if not shutil.which("npm") and not shutil.which("npx"):
            print("  [!]  mcporter requires Node.js. Install Node.js first:")
            print("     https://nodejs.org/ or: curl -fsSL https://fnm.vercel.app/install | bash")
            return
        try:
            subprocess.run(
                ["npm", "install", "-g", "mcporter"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except Exception as exc:
            print(f"  [X] mcporter install failed: {exc}")
            return
        if shutil.which("mcporter"):
            print("  ✅ mcporter installed")
        else:
            print(
                "  [X] mcporter install failed. Retry: npm install -g mcporter "
                "(check network/timeout), or try: npx mcporter@latest list"
            )
            return

    try:
        result = subprocess.run(
            ["mcporter", "config", "list"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
        if "exa" not in result.stdout:
            subprocess.run(
                ["mcporter", "config", "add", "exa", "https://mcp.exa.ai/mcp"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=10,
            )
            print("  ✅ Exa search configured (free, no API key needed)")
        else:
            print("  ✅ Exa search already configured")
    except Exception:
        print("  [!]  Could not configure Exa. Run manually: mcporter config add exa https://mcp.exa.ai/mcp")


def install_mcporter_safe() -> None:
    """Safe mode: check mcporter status and print instructions."""
    print("Checking mcporter (safe mode)...")
    if shutil.which("mcporter"):
        print("  ✅ mcporter already installed")
        print("  To configure Exa search: mcporter config add exa https://mcp.exa.ai/mcp")
    else:
        print("  -- mcporter not installed")
        print("  To install: npm install -g mcporter")
        print("  Then configure Exa: mcporter config add exa https://mcp.exa.ai/mcp")


def detect_environment() -> str:
    """Auto-detect if running on a local computer or a server."""
    indicators = 0

    if os.environ.get("SSH_CONNECTION") or os.environ.get("SSH_CLIENT"):
        indicators += 2

    if os.path.exists("/.dockerenv") or os.path.exists("/run/.containerenv"):
        indicators += 2

    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        indicators += 1

    for cloud_file in ("/sys/hypervisor/uuid", "/sys/class/dmi/id/product_name"):
        if not os.path.exists(cloud_file):
            continue
        try:
            with open(cloud_file, encoding="utf-8") as handle:
                content = handle.read().lower()
        except Exception:
            continue
        if any(
            marker in content
            for marker in ("amazon", "google", "microsoft", "digitalocean", "linode", "vultr", "hetzner")
        ):
            indicators += 2

    try:
        result = subprocess.run(
            ["systemd-detect-virt"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=3,
        )
        if result.returncode == 0 and result.stdout.strip() != "none":
            indicators += 1
    except Exception:
        pass

    return "server" if indicators >= 2 else "local"


def install_xiaoyuzhou_deps() -> None:
    """Install Xiaoyuzhou podcast transcription script."""
    config = Config()
    print("Setting up Xiaoyuzhou podcast transcription...")

    tools_dir = os.path.expanduser("~/.agent-reach/tools/xiaoyuzhou")
    script_dst = os.path.join(tools_dir, "transcribe.sh")

    if os.path.isfile(script_dst):
        print("  ✅ Xiaoyuzhou transcription script already installed")
    else:
        script_src = Path(__file__).resolve().parent.parent / "scripts" / "transcribe_xiaoyuzhou.sh"
        if os.path.isfile(script_src):
            try:
                os.makedirs(tools_dir, exist_ok=True)
                shutil.copy2(script_src, script_dst)
                os.chmod(script_dst, 0o755)
                print("  ✅ Xiaoyuzhou transcription script installed")
            except Exception as exc:
                print(f"  [!]  Failed to install script: {exc}")
        else:
            print("  [!]  Script source not found in package")

    if shutil.which("ffmpeg"):
        print("  ✅ ffmpeg available")
    else:
        print("  -- ffmpeg not found. Install: apt install -y ffmpeg (or brew install ffmpeg)")

    has_key = bool(os.environ.get("GROQ_API_KEY")) or bool(config.get("groq_api_key"))
    if has_key:
        print("  ✅ Groq API key configured")
    else:
        print("  -- Groq API key not set. Get free key at https://console.groq.com")
        print("     Then run: agent-reach configure groq-key gsk_xxxxx")


def install_twitter_deps() -> None:
    """Install twitter-cli for Twitter search + timeline."""
    install_with_fallbacks(
        label="Twitter (twitter-cli)",
        success_binary="twitter",
        installer_options=(
            InstallerOption("pipx", ("pipx", "install", "twitter-cli")),
            InstallerOption("uv", ("uv", "tool", "install", "twitter-cli")),
        ),
        already_installed_message="  ✅ twitter-cli already installed",
        success_message="  ✅ twitter-cli installed",
        failure_message="  [!]  twitter-cli install failed. Run: pipx install twitter-cli",
    )


def install_xhs_deps() -> None:
    """Install xhs-cli (xiaohongshu-cli) for XiaoHongShu."""
    install_with_fallbacks(
        label="XiaoHongShu (xhs-cli)",
        success_binary="xhs",
        installer_options=(
            InstallerOption("pipx", ("pipx", "install", "xiaohongshu-cli")),
            InstallerOption("uv", ("uv", "tool", "install", "xiaohongshu-cli")),
        ),
        already_installed_message="  ✅ xhs-cli already installed",
        success_message="  ✅ xhs-cli installed (run `xhs login` to authenticate)",
        failure_message="  [!]  xhs-cli install failed. Run: pipx install xiaohongshu-cli",
    )


def install_reddit_deps() -> None:
    """Install rdt-cli for Reddit search + reading."""
    install_with_fallbacks(
        label="Reddit (rdt-cli)",
        success_binary="rdt",
        installer_options=(
            InstallerOption("pipx", ("pipx", "install", "rdt-cli")),
            InstallerOption("uv", ("uv", "tool", "install", "rdt-cli")),
        ),
        already_installed_message="  ✅ rdt-cli already installed",
        success_message="  ✅ rdt-cli installed",
        failure_message="  [!]  rdt-cli install failed. Run: pipx install rdt-cli",
    )


def install_bili_deps() -> None:
    """Install bili-cli for Bilibili hot/rank/search."""
    install_with_fallbacks(
        label="Bilibili (bili-cli)",
        success_binary="bili",
        installer_options=(
            InstallerOption("pipx", ("pipx", "install", "bilibili-cli")),
            InstallerOption("uv", ("uv", "tool", "install", "bilibili-cli")),
        ),
        already_installed_message="  ✅ bili-cli already installed",
        success_message="  ✅ bili-cli installed",
        failure_message="  [!]  bili-cli install failed. Run: pipx install bilibili-cli",
    )


def install_weibo_deps() -> None:
    """Install Weibo MCP server (Panniantong fork with visitor passport auth)."""
    print("Setting up Weibo MCP server...")

    mcporter = shutil.which("mcporter")
    if mcporter:
        try:
            result = subprocess.run(
                [mcporter, "config", "list"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=5,
            )
        except Exception:
            result = None
        if result and "weibo" in result.stdout:
            print("  ✅ Weibo MCP already configured")
            return

    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "-q", "git+https://github.com/Panniantong/mcp-server-weibo.git"],
            check=True,
            timeout=120,
        )
        print("  ✅ mcp-server-weibo installed (Panniantong fork)")
    except Exception as exc:
        print(f"  [!]  mcp-server-weibo install failed: {exc}")
        return

    if mcporter:
        try:
            subprocess.run(
                [mcporter, "config", "add", "weibo", "--command", "mcp-server-weibo"],
                check=True,
                capture_output=True,
                timeout=10,
            )
            print("  ✅ Weibo MCP registered with mcporter")
        except Exception:
            print(
                "  [!]  mcporter config add failed. Run manually: "
                "mcporter config add weibo --command 'mcp-server-weibo'"
            )
    else:
        print(
            "  -- mcporter not found, skipping MCP registration. Install mcporter first, "
            "then run: mcporter config add weibo --command 'mcp-server-weibo'"
        )


def install_wechat_deps() -> None:
    """Install WeChat article reading and search dependencies."""
    print("Setting up WeChat article tools...")

    has_camoufox = False
    has_miku = False
    try:
        import camoufox  # noqa: F401

        has_camoufox = True
    except ImportError:
        pass
    try:
        import miku_ai  # noqa: F401

        has_miku = True
    except ImportError:
        pass

    if has_camoufox and has_miku:
        print("  ✅ WeChat Python packages already installed")
    else:
        packages: list[str] = []
        if not has_camoufox:
            packages.extend(["camoufox[geoip]", "markdownify", "beautifulsoup4", "httpx"])
        if not has_miku:
            packages.append("miku_ai")
        try:
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "--break-system-packages", "-q", *packages],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=120,
            )
        except Exception:
            print(f"  [!]  WeChat packages install failed. Try: pip install {' '.join(packages)}")
        else:
            if _imports_available("camoufox", "miku_ai"):
                print(f"  ✅ WeChat Python packages installed ({', '.join(packages)})")
            else:
                print(f"  [!]  Some WeChat packages failed to install. Try: pip install {' '.join(packages)}")

    tools_dir = os.path.expanduser("~/.agent-reach/tools")
    wechat_dir = os.path.join(tools_dir, "wechat-article-for-ai")
    if os.path.isfile(os.path.join(wechat_dir, "main.py")):
        print("  ✅ wechat-article-for-ai tool already installed")
        return

    try:
        os.makedirs(tools_dir, exist_ok=True)
        subprocess.run(
            [
                "git",
                "clone",
                "--depth",
                "1",
                "https://github.com/Panniantong/wechat-article-for-ai.git",
                wechat_dir,
            ],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except Exception:
        print(
            "  [!]  wechat-article-for-ai clone failed. Try: "
            f"git clone https://github.com/Panniantong/wechat-article-for-ai.git {wechat_dir}"
        )
        return

    if os.path.isfile(os.path.join(wechat_dir, "main.py")):
        print("  ✅ wechat-article-for-ai tool installed")
    else:
        print(
            "  [!]  wechat-article-for-ai clone failed. Try: "
            f"git clone https://github.com/Panniantong/wechat-article-for-ai.git {wechat_dir}"
        )


def _imports_available(*module_names: str) -> bool:
    if not module_names:
        return True
    import importlib

    try:
        for module_name in module_names:
            importlib.import_module(module_name)
    except ImportError:
        return False
    return True


def _install_gh_cli() -> None:
    if shutil.which("gh"):
        print("  ✅ gh CLI already installed")
        return

    print("  Installing gh CLI...")
    os_type = platform.system().lower()
    if os_type == "linux":
        _install_gh_cli_linux()
    elif os_type == "darwin":
        _install_gh_cli_macos()
    else:
        print("  [!]  gh CLI not found. Install: https://cli.github.com")


def _install_gh_cli_linux() -> None:
    try:
        keyring_path = "/usr/share/keyrings/githubcli-archive-keyring.gpg"
        list_path = "/etc/apt/sources.list.d/github-cli.list"
        arch = subprocess.run(
            ["dpkg", "--print-architecture"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        ).stdout.strip() or "amd64"
        subprocess.run(
            ["curl", "-fsSL", "https://cli.github.com/packages/githubcli-archive-keyring.gpg", "-o", keyring_path],
            capture_output=True,
            timeout=60,
        )
        repo_line = (
            f"deb [arch={arch} signed-by={keyring_path}] "
            "https://cli.github.com/packages stable main\n"
        )
        with open(list_path, "w", encoding="utf-8") as handle:
            handle.write(repo_line)
        subprocess.run(["apt-get", "update", "-qq"], capture_output=True, timeout=60)
        subprocess.run(["apt-get", "install", "-y", "-qq", "gh"], capture_output=True, timeout=60)
    except PermissionError:
        print("  [!]  gh CLI install needs root privileges. Re-run with sudo or install gh manually.")
    except Exception:
        print(
            "  [!]  gh CLI install failed. You can try: snap install gh, or download from "
            "https://github.com/cli/cli/releases"
        )
        return

    if shutil.which("gh"):
        print("  ✅ gh CLI installed")
    else:
        print(
            "  [!]  gh CLI install failed. You can try: snap install gh, or download from "
            "https://github.com/cli/cli/releases"
        )


def _install_gh_cli_macos() -> None:
    if not shutil.which("brew"):
        print("  [!]  gh CLI not found. Install: https://cli.github.com")
        return

    try:
        subprocess.run(["brew", "install", "gh"], capture_output=True, timeout=120)
    except Exception:
        print("  [!]  gh CLI install failed. Try: brew install gh")
        return

    if shutil.which("gh"):
        print("  ✅ gh CLI installed")
    else:
        print("  [!]  gh CLI install failed. Try: brew install gh")


def _install_nodejs() -> None:
    if shutil.which("node") and shutil.which("npm"):
        print("  ✅ Node.js already installed")
        return

    print("  Installing Node.js...")
    script_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".sh") as handle:
            script_path = handle.name
        subprocess.run(
            ["curl", "-fsSL", "https://deb.nodesource.com/setup_22.x", "-o", script_path],
            capture_output=True,
            timeout=60,
        )
        subprocess.run(["bash", script_path], capture_output=True, timeout=120)
        subprocess.run(["apt-get", "install", "-y", "-qq", "nodejs"], capture_output=True, timeout=120)
    except Exception:
        print(
            "  [!]  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, "
            "or download from https://nodejs.org"
        )
        return
    finally:
        if script_path:
            try:
                os.unlink(script_path)
            except Exception:
                pass

    if shutil.which("node"):
        print("  ✅ Node.js installed")
    else:
        print(
            "  [!]  Node.js install failed. Try: apt install nodejs npm, or nvm install 22, "
            "or download from https://nodejs.org"
        )


def _install_undici() -> None:
    npm_cmd = shutil.which("npm")
    if not npm_cmd:
        return

    if npm_global_package_installed("undici"):
        print("  ✅ undici already installed (Node.js proxy support)")
        return

    try:
        subprocess.run(
            [npm_cmd, "install", "-g", "undici"],
            capture_output=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
    except Exception:
        print("  -- undici install failed (optional — may not work behind proxies)")
        return

    if npm_global_package_installed("undici"):
        print("  ✅ undici installed (Node.js proxy support)")
    else:
        print("  -- undici install failed (optional — may not work behind proxies)")


def _configure_ytdlp_runtime() -> None:
    if not shutil.which("node"):
        return

    ytdlp_config_dir = os.path.expanduser("~/.config/yt-dlp")
    ytdlp_config = os.path.join(ytdlp_config_dir, "config")
    needs_config = True
    if os.path.exists(ytdlp_config):
        with open(ytdlp_config, encoding="utf-8") as handle:
            if "--js-runtimes" in handle.read():
                needs_config = False
                print("  ✅ yt-dlp JS runtime already configured")

    if not needs_config:
        return

    try:
        os.makedirs(ytdlp_config_dir, exist_ok=True)
        with open(ytdlp_config, "a", encoding="utf-8") as handle:
            handle.write("--js-runtimes node\n")
        print("  ✅ yt-dlp configured to use Node.js as JS runtime (YouTube)")
    except Exception:
        print("  -- Could not configure yt-dlp JS runtime (YouTube may not work)")
