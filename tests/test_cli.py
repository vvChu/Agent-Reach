# -*- coding: utf-8 -*-
"""Tests for Agent Reach CLI."""

import re
from pathlib import Path
from unittest.mock import patch

import pytest
import requests

import agent_reach.cli as cli
from agent_reach.cli import main


class TestCLI:
    def test_version(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["agent-reach", "version"]):
                main()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        assert "Agent Reach v" in captured.out

    def test_no_command_shows_help(self, capsys):
        with pytest.raises(SystemExit) as exc_info:
            with patch("sys.argv", ["agent-reach"]):
                main()
        assert exc_info.value.code == 0

    def test_doctor_runs(self, capsys):
        with patch("sys.argv", ["agent-reach", "doctor"]):
            main()
        captured = capsys.readouterr()
        assert "Agent Reach" in captured.out
        assert "✅" in captured.out

    def test_parse_twitter_cookie_input_separate_values(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input("token123 ct0abc")
        assert auth_token == "token123"
        assert ct0 == "ct0abc"

    def test_parse_twitter_cookie_input_cookie_header(self):
        auth_token, ct0 = cli._parse_twitter_cookie_input(
            "auth_token=token123; ct0=ct0abc; other=value"
        )
        assert auth_token == "token123"
        assert ct0 == "ct0abc"

    def test_install_dry_run_stays_side_effect_free(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        calls = []

        monkeypatch.setattr(cli, "_detect_environment", lambda: "local")
        monkeypatch.setattr(
            cli,
            "_install_system_deps_dryrun",
            lambda: calls.append("system-dryrun"),
        )
        monkeypatch.setattr(
            cli,
            "_install_system_deps",
            lambda: pytest.fail("non-dry-run system installer should not run"),
        )
        monkeypatch.setattr(
            cli,
            "_install_system_deps_safe",
            lambda: pytest.fail("safe installer should not run in dry-run"),
        )
        monkeypatch.setattr(
            cli,
            "_install_mcporter",
            lambda: pytest.fail("mcporter installer should not run in dry-run"),
        )
        monkeypatch.setattr(
            cli,
            "_install_mcporter_safe",
            lambda: pytest.fail("safe mcporter installer should not run in dry-run"),
        )
        monkeypatch.setattr(
            cli,
            "_install_skill",
            lambda: pytest.fail("skill install should not run in dry-run"),
        )

        with patch(
            "sys.argv",
            ["agent-reach", "install", "--env=auto", "--dry-run", "--channels=twitter"],
        ):
            main()

        captured = capsys.readouterr()
        assert calls == ["system-dryrun"]
        assert "DRY RUN — showing what would be done (no changes)" in captured.out
        assert "[dry-run] Would install mcporter and configure Exa search" in captured.out
        assert "[dry-run] Would install optional channels: twitter" in captured.out
        assert "[dry-run] Would try to import cookies from Chrome/Firefox" in captured.out
        assert "Dry run complete. No changes were made." in captured.out

    def test_install_safe_uses_safe_helpers_and_runs_validation(self, capsys, monkeypatch, tmp_path):
        monkeypatch.setenv("HOME", str(tmp_path))
        calls = []
        fake_results = {"github": {"status": "ok", "name": "GitHub", "message": "ready"}}

        monkeypatch.setattr(
            cli,
            "_install_system_deps_safe",
            lambda: calls.append("system-safe"),
        )
        monkeypatch.setattr(
            cli,
            "_install_mcporter_safe",
            lambda: calls.append("mcporter-safe"),
        )
        monkeypatch.setattr(
            cli,
            "_install_system_deps",
            lambda: pytest.fail("unsafe system installer should not run in safe mode"),
        )
        monkeypatch.setattr(
            cli,
            "_install_mcporter",
            lambda: pytest.fail("unsafe mcporter installer should not run in safe mode"),
        )
        monkeypatch.setattr(cli, "_check_all", lambda _config: fake_results)
        monkeypatch.setattr(cli, "_format_doctor_report", lambda results: f"formatted:{len(results)}")
        monkeypatch.setattr(cli, "_install_skill", lambda: calls.append("skill"))

        with patch("sys.argv", ["agent-reach", "install", "--safe"]):
            main()

        captured = capsys.readouterr()
        assert calls == ["system-safe", "mcporter-safe", "skill"]
        assert "SAFE MODE — skipping automatic system changes" in captured.out
        assert "Testing channels..." in captured.out
        assert "formatted:1" in captured.out
        assert "✅ Installation complete! 1/1 channels active." in captured.out

    def test_environment_detection_prefers_local_when_no_server_indicators(self, monkeypatch):
        monkeypatch.delenv("SSH_CONNECTION", raising=False)
        monkeypatch.delenv("SSH_CLIENT", raising=False)
        monkeypatch.setenv("DISPLAY", ":0")
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setattr("agent_reach.commands.install.os.path.exists", lambda _path: False)

        class Result:
            returncode = 1
            stdout = "none"

        monkeypatch.setattr("agent_reach.commands.install.subprocess.run", lambda *args, **kwargs: Result())

        assert cli._detect_environment() == "local"

    def test_environment_detection_detects_server_from_ssh(self, monkeypatch):
        monkeypatch.setenv("SSH_CONNECTION", "1 2 3 4")
        monkeypatch.delenv("DISPLAY", raising=False)
        monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
        monkeypatch.setattr("agent_reach.commands.install.os.path.exists", lambda _path: False)

        class Result:
            returncode = 1
            stdout = "none"

        monkeypatch.setattr("agent_reach.commands.install.subprocess.run", lambda *args, **kwargs: Result())

        assert cli._detect_environment() == "server"

    def test_version_consistency(self):
        repo_root = Path(__file__).resolve().parents[1]
        pyproject = (repo_root / "pyproject.toml").read_text(encoding="utf-8")
        init_py = (repo_root / "agent_reach" / "__init__.py").read_text(encoding="utf-8")

        pyproject_match = re.search(r'^version = "([^"]+)"$', pyproject, re.MULTILINE)
        init_match = re.search(r'^__version__ = "([^"]+)"$', init_py, re.MULTILINE)

        assert pyproject_match is not None, "Could not find version in pyproject.toml"
        assert init_match is not None, "Could not find __version__ in agent_reach/__init__.py"
        assert pyproject_match.group(1) == init_match.group(1) == cli.__version__


class TestCheckUpdateRetry:
    def test_retry_timeout_classification(self):
        sleeps = []

        def fake_sleep(seconds):
            sleeps.append(seconds)

        with patch("requests.get", side_effect=requests.exceptions.Timeout("timed out")):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                timeout=1,
                retries=3,
                sleeper=fake_sleep,
            )

        assert resp is None
        assert err == "timeout"
        assert attempts == 3
        assert sleeps == [1, 2]

    def test_retry_dns_classification(self):
        error = requests.exceptions.ConnectionError("getaddrinfo failed for api.github.com")
        with patch("requests.get", side_effect=error):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=1,
                sleeper=lambda _x: None,
            )
        assert resp is None
        assert err == "dns"
        assert attempts == 1

    def test_retry_rate_limit_then_success(self):
        sleeps = []

        class R:
            def __init__(self, code, payload=None, headers=None):
                self.status_code = code
                self._payload = payload or {}
                self.headers = headers or {}

            def json(self):
                return self._payload

        sequence = [
            R(429, headers={"Retry-After": "3"}),
            R(200, payload={"tag_name": "v1.4.0"}),
        ]

        with patch("requests.get", side_effect=sequence):
            resp, err, attempts = cli._github_get_with_retry(
                "https://api.github.com/test",
                retries=3,
                sleeper=lambda s: sleeps.append(s),
            )

        assert err is None
        assert resp is not None
        assert resp.status_code == 200
        assert attempts == 2
        assert sleeps == [3.0]

    def test_classify_rate_limit_from_403(self):
        class R:
            status_code = 403
            headers = {"X-RateLimit-Remaining": "0"}

            @staticmethod
            def json():
                return {"message": "API rate limit exceeded"}

        assert cli._classify_github_response_error(R()) == "rate_limit"

    def test_check_update_reports_classified_error(self, capsys):
        with patch("agent_reach.cli._github_get_with_retry", return_value=(None, "timeout", 3)):
            result = cli._cmd_check_update()

        captured = capsys.readouterr()
        assert result == "error"
        assert "网络超时" in captured.out
        assert "已重试 3 次" in captured.out
