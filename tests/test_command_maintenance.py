# -*- coding: utf-8 -*-
"""Isolated tests for maintenance command helpers."""

from __future__ import annotations

from argparse import Namespace

from agent_reach.commands import maintenance


class _StubConfig:
    config_path = "/tmp/config.yaml"

    def __init__(self):
        self.values = {}

    def get(self, key):
        return self.values.get(key)

    def set(self, key, value):
        self.values[key] = value


def test_run_doctor_uses_injected_hooks():
    printed = []
    calls = []

    maintenance.run_doctor(
        config_factory=_StubConfig,
        check_all_fn=lambda _config: {"github": {"status": "ok"}},
        format_report_fn=lambda results: f"report:{len(results)}",
        install_skill=lambda: calls.append("skill"),
        rich_printer_loader=lambda: printed.append,
    )

    assert printed == ["report:1"]
    assert calls == ["skill"]


def test_run_watch_reports_issues_and_available_update(capsys):
    class Response:
        status_code = 200

        @staticmethod
        def json():
            return {"tag_name": "v9.9.9", "body": "line1\nline2"}

    maintenance.run_watch(
        "1.4.0",
        config_factory=_StubConfig,
        check_all_fn=lambda _config: {
            "github": {"status": "ok", "name": "GitHub", "message": "ready"},
            "reddit": {"status": "warn", "name": "Reddit", "message": "login needed"},
        },
        getter=lambda *_args, **_kwargs: (Response(), None, 1),
    )

    captured = capsys.readouterr()
    assert "Agent Reach 监控报告" in captured.out
    assert "[!] Reddit：login needed" in captured.out
    assert "新版本可用: v9.9.9" in captured.out


def test_run_uninstall_dry_run_preserves_files(capsys, tmp_path):
    config_dir = tmp_path / ".agent-reach"
    config_dir.mkdir()
    skill_dir = tmp_path / ".openclaw" / "skills" / "agent-reach"
    skill_dir.mkdir(parents=True)

    maintenance.run_uninstall(
        Namespace(dry_run=True, keep_config=False),
        expanduser=lambda path: path.replace("~", str(tmp_path)),
        isdir=lambda path: __import__("os").path.isdir(path),
        which=lambda _name: None,
    )

    captured = capsys.readouterr()
    assert config_dir.exists()
    assert skill_dir.exists()
    assert "[dry-run] Would remove config directory" in captured.out
    assert "[dry-run] Would remove OpenClaw skill" in captured.out
