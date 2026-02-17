"""xbt plugin for automatic dbt-loom configuration.

Skips plugin management commands like `xbt plugin list`.
"""

import logging
from typing import List, Optional

import pluggy

from .arg_parser import resolve_project_dir
from .config_generator import auto_configure_loom
from .utils import (
    emit_status,
    find_workspace_root,
    format_status_message,
    is_plugin_management_command,
)

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
        if is_plugin_management_command(args):
            logger.debug("Skipping auto-configure for plugin management command")
            return None

        # Resolve project directory
        project_dir = resolve_project_dir(args)

        if not project_dir:
            logger.debug("Could not resolve project directory, skipping dbt-loom config")
            return None

        # Get workspace root (parent of current project or cwd)
        workspace_root = find_workspace_root(project_dir)

        # Auto-configure dbt-loom
        config_file = auto_configure_loom(
            project_dir=project_dir,
            args=args,
            workspace_root=workspace_root,
        )

        if config_file:
            message = format_status_message(
                "xbt-loom-auto-configure",
                f"Generated {config_file.name} in {project_dir.name}/",
            )
            emit_status(logger, message)
        else:
            message = format_status_message(
                "xbt-loom-auto-configure",
                "No dependencies.yml found; no config generated.",
            )
            emit_status(logger, message)

    except Exception as e:
        logger.error("Error in dbt-loom auto-configuration plugin: %s", e, exc_info=True)

    # Always return None to leave args unchanged
    return None

