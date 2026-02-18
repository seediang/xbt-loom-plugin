"""xbt plugin for zipping dbt artifacts after invocation."""

import logging
import zipfile
from typing import List, Optional

import pluggy

from .arg_parser import resolve_project_dir
from .artifact_helpers import (
    extract_dbt_target,
    get_project_name,
    load_artifact_config,
    resolve_profiles_path,
)
from .artifact_storage import get_artifact_storage, should_skip_upload
from .utils import emit_status, format_status_message, is_plugin_management_command

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("xbt")


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
            profiles_path = resolve_profiles_path(project_dir)

            target_name = extract_dbt_target(args, profiles_path)
            project_name = get_project_name(project_dir)
            config = load_artifact_config(project_dir)

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
