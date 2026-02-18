"""CLI commands for artifact storage operations."""

import argparse
import logging
from pathlib import Path
from typing import Optional

from .arg_parser import resolve_project_dir
from .artifact_helpers import (
    extract_dbt_target,
    get_project_name,
    load_artifact_config,
    resolve_profiles_path,
)
from .artifact_storage import get_artifact_storage, should_skip_upload

logger = logging.getLogger(__name__)


def _get_project_dir() -> Optional[Path]:
    """Get the current dbt project directory."""
    project_dir = resolve_project_dir([])
    if project_dir:
        return project_dir

    cwd = Path.cwd()
    if (cwd.parent / "dbt_project.yml").exists():
        return cwd.parent

    for subdir in cwd.iterdir():
        if subdir.is_dir() and (subdir / "dbt_project.yml").exists():
            return subdir

    logger.error("Could not find dbt project directory")
    return None


def push_artifacts(args: argparse.Namespace) -> int:
    """Push current project artifacts to storage backend.

    Args:
        args: Parsed command-line arguments

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        project_dir = _get_project_dir()
        if not project_dir:
            return 1

        project_name = get_project_name(project_dir)
        if not project_name:
            logger.error("Could not determine project name")
            return 1

        target_dir = project_dir / "target"
        manifest_path = target_dir / "manifest.json"
        run_results_path = target_dir / "run_results.json"

        if not manifest_path.exists() or not run_results_path.exists():
            logger.error("manifest.json or run_results.json not found in target/")
            return 1

        # Get target
        profiles_path = resolve_profiles_path(project_dir)

        # Allow CLI override
        if args.target:
            target_name = args.target
        else:
            target_name = extract_dbt_target([], profiles_path)

        config = load_artifact_config(project_dir)

        # Check skip patterns unless --force is used
        if not args.force and should_skip_upload(
            target_name, config.get("upload_skip_patterns", [])
        ):
            logger.info(
                f"Skipping artifact upload for target '{target_name}' "
                f"(matches skip pattern). Use --force to override."
            )
            return 0

        # Initialize storage backend
        storage = get_artifact_storage(
            config.get("backend", "local"),
            target_name,
            project_name,
            config,
        )

        if not storage:
            logger.error(
                f"Could not initialize storage backend: {config.get('backend')}"
            )
            return 1

        # Upload
        if storage.upload(str(manifest_path), str(run_results_path)):
            print(
                f"✓ Successfully uploaded artifacts to {config.get('backend')} "
                f"({target_name}/{project_name})"
            )
            return 0
        else:
            logger.error("Failed to upload artifacts")
            return 1

    except Exception as e:
        logger.error(f"Error pushing artifacts: {e}", exc_info=True)
        return 1


def pull_artifacts(args: argparse.Namespace) -> int:
    """Pull artifacts from storage backend.

    Args:
        args: Parsed command-line arguments (with project name)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        project_dir = _get_project_dir()
        if not project_dir:
            project_dir = Path.cwd()

        config = load_artifact_config(project_dir)

        # Get target
        profiles_path = resolve_profiles_path(project_dir)

        if args.target:
            target_name = args.target
        else:
            target_name = extract_dbt_target([], profiles_path)

        project_name = args.project

        # Initialize storage backend
        storage = get_artifact_storage(
            config.get("backend", "local"),
            target_name,
            project_name,
            config,
        )

        if not storage:
            logger.error(
                f"Could not initialize storage backend: {config.get('backend')}"
            )
            return 1

        # Download
        result = storage.download(version=args.version)

        if result and "manifest_path" in result:
            print(
                f"✓ Successfully downloaded artifacts for {project_name} (target: {target_name})"
            )
            print(f"  Manifest: {result['manifest_path']}")
            print(f"  Run results: {result['run_results_path']}")
            return 0
        else:
            logger.error(f"Failed to download artifacts for {project_name}")
            return 1

    except Exception as e:
        logger.error(f"Error pulling artifacts: {e}", exc_info=True)
        return 1


def list_artifacts(args: argparse.Namespace) -> int:
    """List available artifact versions.

    Args:
        args: Parsed command-line arguments (with project name)

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    try:
        project_dir = _get_project_dir()
        if not project_dir:
            project_dir = Path.cwd()

        config = load_artifact_config(project_dir)

        # Get target
        profiles_path = resolve_profiles_path(project_dir)

        if args.target:
            target_name = args.target
        else:
            target_name = extract_dbt_target([], profiles_path)

        project_name = args.project

        # Initialize storage backend
        storage = get_artifact_storage(
            config.get("backend", "local"),
            target_name,
            project_name,
            config,
        )

        if not storage:
            logger.error(
                f"Could not initialize storage backend: {config.get('backend')}"
            )
            return 1

        # List versions
        versions = storage.list_versions()

        if versions:
            print(f"Available versions for {project_name} (target: {target_name}):")
            for version in versions:
                print(f"  - {version}")
            print("  - latest")
            return 0
        else:
            print(f"No versions found for {project_name} (target: {target_name})")
            return 0

    except Exception as e:
        logger.error(f"Error listing artifacts: {e}", exc_info=True)
        return 1


def main() -> int:
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Manage dbt artifact storage", prog="xbt artifacts"
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # Push command
    push_parser = subparsers.add_parser("push", help="Upload current project artifacts")
    push_parser.add_argument(
        "--target",
        help="Target name (defaults to dbt target from profiles.yml)",
    )
    push_parser.add_argument(
        "--force",
        action="store_true",
        help="Override skip patterns",
    )
    push_parser.set_defaults(func=push_artifacts)

    # Pull command
    pull_parser = subparsers.add_parser(
        "pull", help="Download upstream project artifacts"
    )
    pull_parser.add_argument("project", help="Project name to pull")
    pull_parser.add_argument(
        "--target",
        help="Target name (defaults to dbt target from profiles.yml)",
    )
    pull_parser.add_argument(
        "--version",
        help="Specific version to download (defaults to latest)",
    )
    pull_parser.set_defaults(func=pull_artifacts)

    # List command
    list_parser = subparsers.add_parser("list", help="List available artifact versions")
    list_parser.add_argument("project", help="Project name to list")
    list_parser.add_argument(
        "--target",
        help="Target name (defaults to dbt target from profiles.yml)",
    )
    list_parser.set_defaults(func=list_artifacts)

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 0

    return args.func(args)
