"""xbt plugin for automatic dbt-loom configuration.

Skips plugin management commands like `xbt plugin list`.
"""

import logging
import tempfile
from pathlib import Path

import pluggy

from .arg_parser import resolve_project_dir
from .artifact_helpers import (
    extract_dbt_target,
    load_artifact_config,
    resolve_profiles_path,
)
from .artifact_storage import get_artifact_storage
from .config_generator import auto_configure_loom, read_dependencies_yml
from .utils import (
    emit_status,
    find_workspace_root,
    format_status_message,
    is_plugin_management_command,
)

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("xbt")


def _pull_upstream_artifacts(
    project_dir: Path, args: list[str]
) -> dict[str, dict[str, str]]:
    """Pull artifacts for upstream projects defined in dependencies.yml.

    Args:
        project_dir: Path to dbt project
        args: dbt CLI arguments
    Returns:
        Dictionary mapping project names to their artifact paths
    """
    artifacts = {}

    # Check if project has dependencies
    dependencies = read_dependencies_yml(project_dir)
    if not dependencies:
        logger.debug("No dependencies.yml found")
        return artifacts

    projects = dependencies.get("projects", [])
    if not projects:
        logger.debug("No projects defined in dependencies.yml")
        return artifacts

    # Get target and config
    profiles_path = resolve_profiles_path(project_dir)

    target_name = extract_dbt_target(args, profiles_path)
    config = load_artifact_config(project_dir)

    logger.debug(f"Pulling artifacts for target: {target_name}")

    # Pull artifacts for each upstream project
    for proj in projects:
        if not isinstance(proj, dict) or "name" not in proj:
            continue

        project_name = proj["name"]

        try:
            # Initialize storage backend
            storage = get_artifact_storage(
                config.get("backend", "local"),
                target_name,
                project_name,
                config,
            )

            if not storage:
                logger.warning(
                    f"Could not initialize storage backend for {project_name}"
                )
                continue

            # Create temp directory for artifacts
            with tempfile.TemporaryDirectory(
                prefix=f"xbt_artifacts_{project_name}_"
            ) as temp_dir:
                # Download artifacts
                result = storage.download(version=None, temp_dir=temp_dir)

                if result and "manifest_path" in result:
                    artifacts[project_name] = result
                    logger.info(
                        f"Successfully pulled artifacts for {project_name} "
                        f"from {config.get('backend')} ({target_name})"
                    )
                else:
                    logger.warning(f"Could not find artifacts for {project_name}")

        except Exception as e:
            logger.debug(
                f"Error pulling artifacts for {project_name}: {e}", exc_info=True
            )

    return artifacts


@hookimpl
def xbt_pre_invoke(args: list[str]) -> list[str] | None:
    """
    xbt hook that runs before dbt invocation.

    Automatically generates dbt_loom.config.yml if the project has a
    dependencies.yml file. Downloads artifacts for upstream projects.

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
            logger.debug(
                "Could not resolve project directory, skipping dbt-loom config"
            )
            return None

        # Get workspace root (parent of current project or cwd)
        workspace_root = find_workspace_root(project_dir)

        # Pull upstream artifacts (if any)
        try:
            artifacts = _pull_upstream_artifacts(project_dir, args)
            if artifacts:
                message = format_status_message(
                    "xbt-loom-pull-artifacts",
                    f"Pulled artifacts for {len(artifacts)} upstream project(s)",
                )
                emit_status(logger, message)
        except Exception as e:
            logger.debug(f"Error pulling upstream artifacts: {e}", exc_info=True)

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
        logger.error(
            "Error in dbt-loom auto-configuration plugin: %s", e, exc_info=True
        )

    # Always return None to leave args unchanged
    return None
