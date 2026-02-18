"""Shared utilities for xbt-loom plugins."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

import yaml


DEFAULT_TEMPLATE_NAME = "dbt_loom.config.template.yml"


def is_plugin_management_command(args: Sequence[str]) -> bool:
    """Return True if args contain a plugin management command."""
    return any(arg in {"plugin", "plugins"} for arg in args)


def format_status_message(prefix: str, message: str) -> str:
    """Build a timestamped status message."""
    timestamp = time.strftime("%H:%M:%S")
    return f"{timestamp}  {prefix}: {message}"


def emit_status(
    logger: logging.Logger, message: str, level: int = logging.INFO
) -> None:
    """Log and print a status message."""
    logger.log(level, message)
    print(message)


def read_text_file(file_path: Path) -> str:
    """Read a text file and return its content."""
    with open(file_path, "r") as file:
        return file.read()


def read_yaml_file(file_path: Path) -> Dict[str, Any]:
    """Read a YAML file and return a dictionary."""
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r") as file:
        return yaml.safe_load(file) or {}


def get_template_candidates(
    project_dir: Path,
    workspace_root: Path,
    template_name: str = DEFAULT_TEMPLATE_NAME,
) -> List[Path]:
    """Return candidate template paths in search order."""
    return [
        project_dir / template_name,
        project_dir.parent / template_name,
        workspace_root / template_name,
    ]


def find_workspace_root(
    project_dir: Path,
    max_depth: int = 5,
    markers: Optional[Iterable[str]] = None,
) -> Path:
    """Find workspace root by walking up for marker files or directories."""
    marker_list = (
        list(markers)
        if markers is not None
        else [
            ".git",
            "pyproject.toml",
            DEFAULT_TEMPLATE_NAME,
        ]
    )

    current = project_dir.resolve()
    for _ in range(max_depth):
        if any((current / marker).exists() for marker in marker_list):
            return current

        parent = current.parent
        if parent == current:
            break

        current = parent

    return project_dir
