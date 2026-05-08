"""Formatting-oriented CLI commands."""

from __future__ import annotations

import argparse
import json
import sys
from typing import TextIO


def run_format_command(
    args: argparse.Namespace,
    *,
    stdin: TextIO | None = None,
    stderr: TextIO | None = None,
) -> None:
    """Clean and format platform API output from stdin."""
    input_stream = stdin or sys.stdin
    error_stream = stderr or sys.stderr

    if args.platform == "xhs":
        from agent_reach.channels.xiaohongshu import format_xhs_result

        raw = input_stream.read().strip()
        if not raw:
            print("Error: no input on stdin", file=error_stream)
            sys.exit(1)
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            print(f"Error: invalid JSON: {exc}", file=error_stream)
            sys.exit(1)

        cleaned = format_xhs_result(data)
        print(json.dumps(cleaned, ensure_ascii=False, indent=2))
