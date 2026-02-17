"""xbt plugin for automatic dbt-loom configuration.

Skips plugin management commands like `xbt plugin list`.
"""

import logging
import time
from pathlib import Path
from typing import List, Optional

import pluggy

from .arg_parser import resolve_project_dir
from .config_generator import auto_configure_loom

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("xbt")


@hookimpl
def xbt_pre_invoke(args: List[str]) -> Optional[List[str]]:
    """
    xbt hook that runs before dbt invocation.

    Automatically generates dbt_loom.config.yml if the project has a
    dependencies.yml file.

    Search order for project directory:
    1. --project-dir CLI flag
    2. DBT_PROJECT_DIR environment variable
    3. Current working directory

    Args:
        args: List of CLI arguments passed to dbt

    Returns:
        None (leaves args unchanged) or the modified args list
    """
    try:
        if _is_plugin_management_command(args):
            logger.debug("Skipping auto-configure for plugin management command")
            return None

        # Resolve project directory
        project_dir = resolve_project_dir(args)

        if not project_dir:
            logger.debug("Could not resolve project directory, skipping dbt-loom config")
            return None

        # Get workspace root (parent of current project or cwd)
        workspace_root = _find_workspace_root(project_dir)

        # Auto-configure dbt-loom
        config_file = auto_configure_loom(
            project_dir=project_dir,
            args=args,
            workspace_root=workspace_root,
        )

        timestamp = time.strftime("%H:%M:%S")
        if config_file:
            message = (
                f"{timestamp}  xbt-loom-auto-configure: Generated {config_file.name} "
                f"in {project_dir.name}/"
            )
            logger.info(message)
            print(message)
        else:
            message = (
                f"{timestamp}  xbt-loom-auto-configure: No dependencies.yml found; "
                "no config generated."
            )
            logger.info(message)
            print(message)

    except Exception as e:
        logger.error("Error in dbt-loom auto-configuration plugin: %s", e, exc_info=True)

    # Always return None to leave args unchanged
    return None


def _is_plugin_management_command(args: List[str]) -> bool:
    return any(arg in {"plugin", "plugins"} for arg in args)


def _find_workspace_root(project_dir: Path, max_depth: int = 5) -> Path:
    """
    Find workspace root by looking for common markers.

    Searches up to max_depth levels for:
    - .git directory
    - pyproject.toml with xbt dependency
    - dbt_loom.config.template.yml

    Falls back to parent directory or project directory itself.

    Args:
        project_dir: Starting directory (typically dbt project)
        max_depth: Maximum levels to search up

    Returns:
        Path to workspace root or project_dir if not found
    """
    current = project_dir.resolve()

    for _ in range(max_depth):
        # Check for .git
        if (current / ".git").exists():
            return current

        # Check for pyproject.toml
        if (current / "pyproject.toml").exists():
            return current

        # Check for template file
        if (current / "dbt_loom.config.template.yml").exists():
            return current

        parent = current.parent
        if parent == current:
            # Reached root filesystem
            break

        current = parent

    return project_dir
