# -*- coding: utf-8 -*-
"""Isolated tests for configure command helpers."""

from __future__ import annotations

from argparse import Namespace

from agent_reach.commands import configure


class _StubConfig:
    def __init__(self):
        self.values = {}

    def set(self, key, value):
        self.values[key] = value


def test_run_configure_from_browser_reports_success(capsys):
    config = _StubConfig()

    configure.run_configure(
        Namespace(from_browser="chrome", key=None, value=[]),
        config_factory=lambda: config,
        browser_configurer=lambda browser, _config: [
            ("Twitter", True, f"loaded from {browser}"),
            ("XHS", False, "not logged in"),
        ],
    )

    captured = capsys.readouterr()
    assert "Extracting cookies from chrome..." in captured.out
    assert "✅ Cookies configured!" in captured.out
    assert config.values == {}


def test_run_configure_twitter_cookies_sets_config_and_checks_access(capsys):
    config = _StubConfig()
    calls = []

    class Result:
        stdout = "ok: true"
        stderr = ""

    def fake_run(command, **kwargs):
        calls.append((command, kwargs))
        return Result()

    configure.run_configure(
        Namespace(from_browser=None, key="twitter-cookies", value=["token123", "ct0abc"]),
        config_factory=lambda: config,
        which=lambda _name: "/usr/bin/twitter",
        run_subprocess=fake_run,
        environ={"PATH": "/usr/bin"},
    )

    captured = capsys.readouterr()
    assert config.values == {
        "twitter_auth_token": "token123",
        "twitter_ct0": "ct0abc",
    }
    assert "✅ Twitter cookies configured!" in captured.out
    assert "✅ Twitter access works!" in captured.out
    assert calls[0][0] == ["/usr/bin/twitter", "status"]
    assert calls[0][1]["env"]["TWITTER_AUTH_TOKEN"] == "token123"
    assert calls[0][1]["env"]["TWITTER_CT0"] == "ct0abc"


def test_xhs_cookies_no_docker_writes_file(capsys, tmp_path):
    written_permissions = []

    def fake_chmod(path, file_mode):
        written_permissions.append((path, file_mode))

    configure.configure_xhs_cookies(
        "a=1; b=2",
        expanduser=lambda path: path.replace("~", str(tmp_path)),
        which=lambda _name: None,
        chmod=fake_chmod,
    )

    cookie_path = tmp_path / ".agent-reach" / "xhs-cookies.json"
    captured = capsys.readouterr()
    assert cookie_path.exists()
    assert "Cookies saved to" in captured.out
    assert written_permissions == [(str(cookie_path), 0o600)]
