"""xbt plugin for zipping dbt artifacts after invocation."""

import logging
import os
from pathlib import Path
from typing import List, Optional
import zipfile

import pluggy
import yaml

from .arg_parser import resolve_project_dir
from .artifact_storage import get_artifact_storage, should_skip_upload
from .utils import emit_status, format_status_message, is_plugin_management_command

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("xbt")


def _extract_dbt_target(args: List[str], profiles_path: Path) -> str:
    """Extract dbt target name from CLI args or profiles.yml.

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


def _get_project_name(project_dir: Path) -> Optional[str]:
    """Extract project name from dbt_project.yml.

    Args:
        project_dir: Path to dbt project directory

    Returns:
        Project name or None if not found
    """
    try:
        dbt_project_yml = project_dir / "dbt_project.yml"
        if dbt_project_yml.exists():
            with open(dbt_project_yml, "r") as f:
                config = yaml.safe_load(f)
                if config:
                    return config.get("name")
    except Exception as e:
        logger.debug(f"Could not read project name from dbt_project.yml: {e}")

    return None


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
        "upload_skip_patterns": [],
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


@hookimpl
def xbt_post_invoke(args: List[str], result: Optional[object] = None) -> None:
    """
    xbt hook that runs after dbt invocation.

    Creates a zip file containing manifest.json and run_results.json from the
    dbt target/ directory, and uploads to configured artifact storage backend.

    Args:
        args: List of CLI arguments passed to dbt
        result: Optional result from dbt invocation (unused)
    """
    try:
        if is_plugin_management_command(args):
            logger.debug("Skipping artifact zip for plugin management command")
            return

        project_dir = resolve_project_dir(args)
        if not project_dir:
            logger.debug("Could not resolve project directory, skipping artifact zip")
            return

        if not project_dir.exists():
            logger.debug("Project directory does not exist, skipping artifact zip")
            return

        target_dir = project_dir / "target"
        expected_files = ["manifest.json", "run_results.json"]
        found_files = [name for name in expected_files if (target_dir / name).exists()]

        if not found_files:
            message = format_status_message(
                "xbt-loom-zip-artifacts",
                "No manifest.json or run_results.json found; skipping zip.",
            )
            emit_status(logger, message)
            return

        # Create zip file (preserved for backward compatibility)
        zip_path = project_dir / "dbt_artifacts.zip"
        with zipfile.ZipFile(
            zip_path, mode="w", compression=zipfile.ZIP_DEFLATED
        ) as zipf:
            for name in found_files:
                zipf.write(target_dir / name, arcname=name)

        message = format_status_message(
            "xbt-loom-zip-artifacts",
            f"Saved {len(found_files)} file(s) to {zip_path}.",
        )
        emit_status(logger, message)

        # New: Upload to configured artifact storage backend
        try:
            profiles_dir = project_dir / "profiles.yml"
            if not profiles_dir.exists():
                profiles_dir = project_dir.parent / "profiles.yml"

            target_name = _extract_dbt_target(args, profiles_dir)
            project_name = _get_project_name(project_dir)
            config = _load_artifact_config(project_dir)

            if not project_name:
                logger.debug(
                    "Could not determine project name, skipping artifact upload"
                )
                return

            # Check skip patterns
            if should_skip_upload(target_name, config.get("upload_skip_patterns", [])):
                logger.info(
                    f"Skipping artifact upload for target '{target_name}' (matches skip pattern)"
                )
                return

            # Initialize storage backend
            storage = get_artifact_storage(
                config.get("backend", "local"),
                target_name,
                project_name,
                config,
            )

            if storage:
                manifest_path = target_dir / "manifest.json"
                run_results_path = target_dir / "run_results.json"

                if storage.upload(str(manifest_path), str(run_results_path)):
                    message = format_status_message(
                        "xbt-loom-artifacts-upload",
                        f"Uploaded artifacts to {config.get('backend', 'local')} "
                        f"({target_name}/{project_name})",
                    )
                    emit_status(logger, message)
                else:
                    logger.warning("Failed to upload artifacts to storage backend")
            else:
                logger.warning(
                    f"Could not initialize storage backend: {config.get('backend')}"
                )
        except Exception as e:
            logger.debug(f"Error uploading artifacts to storage: {e}", exc_info=True)

    except Exception as e:
        logger.error("Error in dbt-loom artifact zip plugin: %s", e, exc_info=True)
