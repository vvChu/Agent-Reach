"""Configuration-related CLI commands."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Mapping
from typing import Any

from agent_reach.config import Config
from agent_reach.cookie_extract import configure_from_browser


def _is_cookie_object(value: object) -> bool:
    return isinstance(value, dict) and "name" in value and "value" in value


def run_configure(
    args: argparse.Namespace,
    *,
    config_factory=Config,
    browser_configurer=configure_from_browser,
    which=shutil.which,
    run_subprocess=subprocess.run,
    environ: Mapping[str, str] | None = None,
) -> None:
    """Set a config value and optionally validate it."""
    env = environ or os.environ
    config = config_factory()

    if args.from_browser:
        browser = args.from_browser
        print(f"Extracting cookies from {browser}...")
        print()

        results = browser_configurer(browser, config)
        found_any = False
        for platform, success, message in results:
            if success:
                print(f"  ✅ {platform}: {message}")
                found_any = True
            else:
                print(f"  -- {platform}: {message}")

        print()
        if found_any:
            print("✅ Cookies configured! Run `agent-reach doctor` to see updated status.")
        else:
            print(f"No cookies found. Make sure you're logged into the platforms in {browser}.")
        return

    if not args.key:
        print("Usage: agent-reach configure <key> <value>")
        print("   or: agent-reach configure --from-browser chrome")
        return

    value = " ".join(args.value) if args.value else ""
    if not value:
        print(f"Missing value for {args.key}")
        return

    if args.key == "proxy":
        config.set("bilibili_proxy", value)
        print("✅ Proxy configured for Bilibili!")
        print("  Note: Reddit 已改为通过 rdt-cli 访问，无需代理。")

    elif args.key == "twitter-cookies":
        auth_token, ct0 = parse_twitter_cookie_input(value)

        if auth_token and ct0:
            config.set("twitter_auth_token", auth_token)
            config.set("twitter_ct0", ct0)

            print("✅ Twitter cookies configured!")
            print("Testing Twitter access...", end=" ")
            try:
                twitter_bin = which("twitter")
                if not twitter_bin:
                    print("[!] twitter-cli not installed. Run: pipx install twitter-cli")
                else:
                    twitter_env = dict(env)
                    twitter_env["TWITTER_AUTH_TOKEN"] = auth_token
                    twitter_env["TWITTER_CT0"] = ct0
                    result = run_subprocess(
                        [twitter_bin, "status"],
                        capture_output=True,
                        encoding="utf-8",
                        errors="replace",
                        timeout=15,
                        env=twitter_env,
                    )
                    output = (result.stdout or "") + (result.stderr or "")
                    if "ok: true" in output:
                        print("✅ Twitter access works!")
                    else:
                        print("[!] Auth check failed (cookies might be wrong)")
            except Exception as exc:
                print(f"[X] Failed: {exc}")
        else:
            print("[X] Could not find auth_token and ct0 in your input.")
            print("   Accepted formats:")
            print("   1. agent-reach configure twitter-cookies AUTH_TOKEN CT0")
            print('   2. agent-reach configure twitter-cookies "auth_token=xxx; ct0=yyy; ..."')

    elif args.key == "youtube-cookies":
        config.set("youtube_cookies_from", value)
        print(f"✅ YouTube cookie source configured: {value}")
        print("   yt-dlp will use cookies from this browser for age-restricted/member videos.")

    elif args.key == "xhs-cookies":
        configure_xhs_cookies(value, which=which, run_subprocess=run_subprocess)

    elif args.key == "github-token":
        config.set("github_token", value)
        print("✅ GitHub token configured!")

    elif args.key == "groq-key":
        config.set("groq_api_key", value)
        print("✅ Groq key configured!")


def parse_twitter_cookie_input(value: str) -> tuple[str | None, str | None]:
    """Parse Twitter cookie input from separate values or a cookie header."""
    auth_token = None
    ct0 = None

    if "auth_token=" in value and "ct0=" in value:
        for part in value.replace(";", " ").split():
            if part.startswith("auth_token="):
                auth_token = part.split("=", 1)[1]
            elif part.startswith("ct0="):
                ct0 = part.split("=", 1)[1]
    elif len(value.split()) == 2 and "=" not in value:
        auth_token, ct0 = value.split()

    return auth_token, ct0


def configure_xhs_cookies(
    value: str,
    *,
    expanduser=os.path.expanduser,
    which=shutil.which,
    run_subprocess=subprocess.run,
    unlink=os.unlink,
    chmod=os.chmod,
) -> None:
    """Import XHS cookies into Docker or save them locally for manual import."""
    raw_value = value.strip()
    if not raw_value:
        print("[X] Missing cookie value.")
        print("   Usage: agent-reach configure xhs-cookies '<cookie JSON or header string>'")
        return

    cookies_json: str | None = None

    if raw_value.startswith("["):
        try:
            parsed = json.loads(raw_value)
            if isinstance(parsed, list) and parsed:
                first = parsed[0]
                if _is_cookie_object(first):
                    cookies_json = json.dumps(parsed)
                    print(f"  Parsed {len(parsed)} cookies from JSON format")
                else:
                    print("[X] JSON array doesn't contain cookie objects (need name/value fields)")
                    return
            else:
                print("[X] Empty or invalid JSON array")
                return
        except json.JSONDecodeError as exc:
            print(f"[X] Invalid JSON: {exc}")
            return

    if cookies_json is None and "=" in raw_value:
        cookies: list[dict[str, Any]] = []
        for part in raw_value.split(";"):
            chunk = part.strip()
            if "=" not in chunk:
                continue
            name, cookie_value = chunk.split("=", 1)
            name = name.strip()
            cookie_value = cookie_value.strip()
            if name:
                cookies.append(
                    {
                        "name": name,
                        "value": cookie_value,
                        "domain": ".xiaohongshu.com",
                        "path": "/",
                        "expires": -1,
                        "size": len(name) + len(cookie_value),
                        "httpOnly": False,
                        "secure": False,
                        "session": True,
                        "sameSite": "Lax",
                    }
                )
        if cookies:
            cookies_json = json.dumps(cookies)
            print(f"  Parsed {len(cookies)} cookies from Header String format")
        else:
            print("[X] Could not parse any cookies from input")
            return

    if not cookies_json:
        print("[X] Could not parse cookies. Accepted formats:")
        print('   1. JSON array: \'[{"name":"x","value":"y","domain":".xiaohongshu.com",...}]\'')
        print('   2. Header String: "key1=val1; key2=val2; ..."')
        return

    docker = which("docker")
    if not docker:
        cookie_path = expanduser("~/.agent-reach/xhs-cookies.json")
        os.makedirs(os.path.dirname(cookie_path), exist_ok=True)
        with open(cookie_path, "w", encoding="utf-8") as handle:
            handle.write(cookies_json)
        chmod(cookie_path, 0o600)
        print(f"  Cookies saved to {cookie_path}")
        print("  Docker not found. Copy manually:")
        print(f"  docker cp {cookie_path} xiaohongshu-mcp:/app/data/cookies.json")
        return

    try:
        result = run_subprocess(
            [docker, "ps", "--filter", "name=xiaohongshu-mcp", "--format", "{{.Names}}"],
            capture_output=True,
            encoding="utf-8",
            timeout=5,
        )
        container_name = result.stdout.strip()
        if not container_name:
            print("[X] xiaohongshu-mcp container is not running.")
            print("   Start it first:")
            print("   docker run -d --name xiaohongshu-mcp -p 18060:18060 xpzouying/xiaohongshu-mcp")
            return
    except Exception as exc:
        print(f"[X] Could not check Docker: {exc}")
        return

    try:
        result = run_subprocess(
            [docker, "exec", container_name, "printenv", "COOKIES_PATH"],
            capture_output=True,
            encoding="utf-8",
            timeout=5,
        )
        cookie_path_in_container = result.stdout.strip() or "/app/cookies.json"
    except Exception:
        cookie_path_in_container = "/app/cookies.json"

    try:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as handle:
            handle.write(cookies_json)
            tmp_path = handle.name

        result = run_subprocess(
            [docker, "cp", tmp_path, f"{container_name}:{cookie_path_in_container}"],
            capture_output=True,
            encoding="utf-8",
            timeout=10,
        )
        unlink(tmp_path)

        if result.returncode != 0:
            print(f"[X] Failed to copy cookies: {result.stderr}")
            return

        print(f"✅ Cookies written to {container_name}:{cookie_path_in_container}")
        print("  Restarting container to reload cookies...", end=" ", flush=True)
        try:
            run_subprocess(
                [docker, "restart", container_name],
                capture_output=True,
                encoding="utf-8",
                timeout=30,
            )
            print("done")
        except Exception as exc:
            print(f"\n  [!] Could not restart container: {exc}")
            print(f"  Restart manually: docker restart {container_name}")
    except Exception as exc:
        print(f"[X] Failed to write cookies: {exc}")
        return

    mcporter = which("mcporter")
    if mcporter:
        print("  Verifying login status...", end=" ")
        try:
            result = run_subprocess(
                [mcporter, "call", "xiaohongshu.check_login_status()"],
                capture_output=True,
                encoding="utf-8",
                errors="replace",
                timeout=15,
            )
            if "已登录" in result.stdout or "logged" in result.stdout.lower():
                print("✅ Login verified!")
            else:
                print("[!] Login check returned unexpected result:")
                print(f"  {result.stdout.strip()[:200]}")
                print("  Cookies were written but login might not be valid. Try fresh cookies.")
        except Exception as exc:
            print(f"[!] Could not verify: {exc}")
    else:
        print("  (mcporter not found, skipping verification)")
