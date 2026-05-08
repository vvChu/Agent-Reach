"""CLI command helpers."""

from __future__ import annotations

import argparse
from collections.abc import Callable, Mapping
from typing import Any

CommandHandler = Callable[[argparse.Namespace], Any]


def dispatch_command(args: argparse.Namespace, handlers: Mapping[str, CommandHandler]) -> Any:
    """Dispatch a parsed CLI command to its handler."""
    handler = handlers.get(args.command)
    if handler is None:
        raise ValueError(f"Unknown command: {args.command}")
    return handler(args)
