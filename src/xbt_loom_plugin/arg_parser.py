"""Parse dbt CLI arguments and environment variables to locate project and profiles directories."""

import os
from pathlib import Path
from typing import Optional, Dict, Any


def parse_cli_args(args: list) -> Dict[str, Optional[str]]:
    """
    Parse CLI arguments following dbt's conventions.

    Searches for:
    - --project-dir (or --project_dir)
    - --profiles-dir (or --profiles_dir)

    Handles both formats: --flag value and --flag=value

    Args:
        args: List of command-line arguments

    Returns:
        Dictionary with keys 'project_dir' and 'profiles_dir' containing found values or None
    """
    result = {"project_dir": None, "profiles_dir": None}

    i = 0
    while i < len(args):
        arg = args[i]

        # Handle --flag=value format
        if "=" in arg:
            flag, value = arg.split("=", 1)
            if flag in ("--project-dir", "--project_dir"):
                result["project_dir"] = value
            elif flag in ("--profiles-dir", "--profiles_dir"):
                result["profiles_dir"] = value
            i += 1

        # Handle --flag value format
        elif arg in ("--project-dir", "--project_dir"):
            if i + 1 < len(args):
                result["project_dir"] = args[i + 1]
                i += 2
            else:
                i += 1

        elif arg in ("--profiles-dir", "--profiles_dir"):
            if i + 1 < len(args):
                result["profiles_dir"] = args[i + 1]
                i += 2
            else:
                i += 1

        else:
            i += 1

    return result


def find_profiles_dir() -> Optional[Path]:
    """
    Find profiles directory following dbt's search order:
    1. Current working directory (profiles.yml exists)
    2. ~/.dbt/ directory
    3. None if not found

    Note: --profiles-dir flag and DBT_PROFILES_DIR env var are handled separately
    in resolve_profiles_dir()

    Returns:
        Path object if found, None otherwise
    """
    # Check current working directory
    cwd_profiles = Path.cwd() / "profiles.yml"
    if cwd_profiles.exists():
        return Path.cwd()

    # Check ~/.dbt/
    home_dbt = Path.home() / ".dbt"
    if home_dbt.exists():
        return home_dbt

    return None


def find_project_dir() -> Optional[Path]:
    """
    Find project directory by looking for dbt_project.yml.

    Searches:
    1. Current working directory

    Returns:
        Path object if dbt_project.yml found, None otherwise
    """
    cwd_project = Path.cwd() / "dbt_project.yml"
    if cwd_project.exists():
        return Path.cwd()

    return None


def resolve_profiles_dir(args: list) -> Optional[Path]:
    """
    Resolve profiles directory following dbt's search order:
    1. --profiles-dir CLI flag
    2. DBT_PROFILES_DIR environment variable
    3. Current working directory (if profiles.yml exists)
    4. ~/.dbt/ directory

    Args:
        args: List of command-line arguments

    Returns:
        Path object if found, None otherwise
    """
    cli_args = parse_cli_args(args)

    # 1. CLI flag
    if cli_args["profiles_dir"]:
        profiles_path = Path(cli_args["profiles_dir"]).resolve()
        return profiles_path

    # 2. Environment variable
    env_profiles_dir = os.getenv("DBT_PROFILES_DIR")
    if env_profiles_dir:
        profiles_path = Path(env_profiles_dir).resolve()
        return profiles_path

    # 3. Current working directory or 4. ~/.dbt/
    return find_profiles_dir()


def resolve_project_dir(args: list) -> Optional[Path]:
    """
    Resolve project directory following dbt's search order:
    1. --project-dir CLI flag
    2. DBT_PROJECT_DIR environment variable
    3. Current working directory (if dbt_project.yml exists)

    Args:
        args: List of command-line arguments

    Returns:
        Path object to project directory if found, None otherwise
    """
    cli_args = parse_cli_args(args)

    # 1. CLI flag
    if cli_args["project_dir"]:
        project_path = Path(cli_args["project_dir"]).resolve()
        return project_path

    # 2. Environment variable
    env_project_dir = os.getenv("DBT_PROJECT_DIR")
    if env_project_dir:
        project_path = Path(env_project_dir).resolve()
        return project_path

    # 3. Current working directory
    return find_project_dir()
