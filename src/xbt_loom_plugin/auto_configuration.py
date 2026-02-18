"""xbt plugin for automatic dbt-loom configuration.

Skips plugin management commands like `xbt plugin list`.
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import List, Optional

import pluggy
import yaml

from .arg_parser import resolve_project_dir
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


def _extract_dbt_target_for_pull(args: List[str], profiles_path: Path) -> str:
    """Extract dbt target name for artifact pulling.

    Args:
        args: dbt CLI arguments
        profiles_path: Path to profiles.yml

    Returns:
        Target name or None if not found
    """
    # Check for --target in args
    for i, arg in enumerate(args):
        if arg == "--target" and i + 1 < len(args):
            return args[i + 1]

    # Check environment variable
    env_target = os.environ.get("XBT_ARTIFACT_TARGET")
    if env_target:
        return env_target

    # Try to get default target from profiles.yml
    try:
        if profiles_path.exists():
            with open(profiles_path, "r") as f:
                profiles = yaml.safe_load(f)
                if profiles:
                    # Get the default profile outputs
                    for profile_name, profile_config in profiles.items():
                        if isinstance(profile_config, dict):
                            outputs = profile_config.get("outputs", {})
                            if isinstance(outputs, dict):
                                for target_name, target_config in outputs.items():
                                    if target_config.get("target") == target_name or (
                                        not target_config.get("target")
                                        and list(outputs.keys())[0] == target_name
                                    ):
                                        return target_name
                                # Return first output as default
                                if outputs:
                                    return list(outputs.keys())[0]
    except Exception as e:
        logger.debug(f"Could not read target from profiles.yml: {e}")

    # Default fallback
    return "dev"


def _load_artifact_config(project_dir: Path) -> dict:
    """Load artifact storage configuration.

    Looks for config in pyproject.toml [tool.xbt-loom.artifacts] section.
    Falls back to environment variables for sensitive data.

    Args:
        project_dir: Path to dbt project directory

    Returns:
        Configuration dict with keys like backend, local_path, bucket_name, etc.
    """
    config = {
        "backend": os.environ.get("XBT_ARTIFACT_BACKEND", "local"),
        "local_path": os.environ.get("XBT_ARTIFACT_LOCAL_PATH", "/tmp/xbt_artifacts"),
        "bucket_name": os.environ.get("XBT_ARTIFACT_S3_BUCKET"),
        "aws_region": os.environ.get("XBT_ARTIFACT_AWS_REGION", "us-east-1"),
        "stage_path": os.environ.get("XBT_ARTIFACT_SNOWFLAKE_STAGE"),
    }

    # Try to load from pyproject.toml
    pyproject_path = Path.cwd() / "pyproject.toml"
    if pyproject_path.exists():
        try:
            import tomllib

            with open(pyproject_path, "rb") as f:
                pyproject = tomllib.load(f)
                artifact_config = (
                    pyproject.get("tool", {}).get("xbt-loom", {}).get("artifacts", {})
                )
                if artifact_config:
                    config.update(artifact_config)
        except ImportError:
            # Python < 3.11, try tomli
            try:
                import tomli  # type: ignore[import-untyped]

                with open(pyproject_path, "rb") as f:
                    pyproject = tomli.load(f)
                    artifact_config = (
                        pyproject.get("tool", {})
                        .get("xbt-loom", {})
                        .get("artifacts", {})
                    )
                    if artifact_config:
                        config.update(artifact_config)
            except Exception as e:
                logger.debug(f"Could not load pyproject.toml: {e}")
        except Exception as e:
            logger.debug(f"Could not load pyproject.toml: {e}")

    return config


def _pull_upstream_artifacts(
    project_dir: Path, args: List[str], workspace_root: Path
) -> dict:
    """Pull artifacts for upstream projects defined in dependencies.yml.

    Args:
        project_dir: Path to dbt project
        args: dbt CLI arguments
        workspace_root: Path to workspace root

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
    profiles_dir = project_dir / "profiles.yml"
    if not profiles_dir.exists():
        profiles_dir = project_dir.parent / "profiles.yml"

    target_name = _extract_dbt_target_for_pull(args, profiles_dir)
    config = _load_artifact_config(project_dir)

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
def xbt_pre_invoke(args: List[str]) -> Optional[List[str]]:
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
            artifacts = _pull_upstream_artifacts(project_dir, args, workspace_root)
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
