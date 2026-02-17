"""xbt plugin for zipping dbt artifacts after invocation."""

import logging
import time
from pathlib import Path
from typing import List, Optional
import zipfile

import pluggy

from .arg_parser import resolve_project_dir

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
        if _is_plugin_management_command(args):
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

        timestamp = time.strftime("%H:%M:%S")
        if not found_files:
            message = (
                f"{timestamp}  xbt-loom-zip-artifacts: No manifest.json or run_results.json "
                "found; skipping zip."
            )
            logger.info(message)
            print(message)
            return

        zip_path = project_dir / "dbt_artifacts.zip"
        with zipfile.ZipFile(zip_path, mode="w", compression=zipfile.ZIP_DEFLATED) as zipf:
            for name in found_files:
                zipf.write(target_dir / name, arcname=name)

        message = (
            f"{timestamp}  xbt-loom-zip-artifacts: Saved {len(found_files)} file(s) "
            f"to {zip_path}."
        )
        logger.info(message)
        print(message)
    except Exception as e:
        logger.error("Error in dbt-loom artifact zip plugin: %s", e, exc_info=True)


def _is_plugin_management_command(args: List[str]) -> bool:
    return any(arg in {"plugin", "plugins"} for arg in args)
