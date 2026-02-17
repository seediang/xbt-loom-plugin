"""xbt plugin for zipping dbt artifacts after invocation."""

import logging
from typing import List, Optional
import zipfile

import pluggy

from .arg_parser import resolve_project_dir
from .utils import emit_status, format_status_message, is_plugin_management_command

logger = logging.getLogger(__name__)
hookimpl = pluggy.HookimplMarker("xbt")


@hookimpl
def xbt_post_invoke(args: List[str], result: Optional[object] = None) -> None:
    """
    xbt hook that runs after dbt invocation.

    Creates a zip file containing manifest.json and run_results.json from the
    dbt target/ directory.

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

        zip_path = project_dir / "dbt_artifacts.zip"
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for name in found_files:
                zipf.write(target_dir / name, arcname=name)

        message = format_status_message(
            "xbt-loom-zip-artifacts",
            f"Saved {len(found_files)} file(s) to {zip_path}.",
        )
        emit_status(logger, message)
    except Exception as e:
        logger.error("Error in dbt-loom artifact zip plugin: %s", e, exc_info=True)

