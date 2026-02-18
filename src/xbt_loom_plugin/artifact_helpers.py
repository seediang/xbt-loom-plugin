"""Shared helpers for artifact target/config/project resolution."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

logger = logging.getLogger(__name__)


def extract_dbt_target(args: List[str], profiles_path: Path) -> str:
    """Extract dbt target from args, env, or profiles.yml with a dev fallback."""
    for index, arg in enumerate(args):
        if arg == "--target" and index + 1 < len(args):
            return args[index + 1]
        if arg.startswith("--target="):
            return arg.split("=", 1)[1]

    env_target = os.environ.get("XBT_LOOM_ARTIFACT_TARGET")
    if env_target:
        return env_target

    try:
        if profiles_path.exists():
            with open(profiles_path, "r") as handle:
                profiles = yaml.safe_load(handle)
            if isinstance(profiles, dict):
                for profile_config in profiles.values():
                    if not isinstance(profile_config, dict):
                        continue
                    outputs = profile_config.get("outputs", {})
                    if not isinstance(outputs, dict) or not outputs:
                        continue

                    for target_name, target_config in outputs.items():
                        if isinstance(target_config, dict) and (
                            target_config.get("target") == target_name
                        ):
                            return target_name

                    return next(iter(outputs.keys()))
    except Exception as error:
        logger.debug("Could not read target from profiles.yml: %s", error)

    return "dev"


def get_project_name(project_dir: Path) -> Optional[str]:
    """Read dbt project name from dbt_project.yml."""
    try:
        dbt_project_yml = project_dir / "dbt_project.yml"
        if not dbt_project_yml.exists():
            return None

        with open(dbt_project_yml, "r") as handle:
            config = yaml.safe_load(handle)
        if isinstance(config, dict):
            name = config.get("name")
            if isinstance(name, str) and name.strip():
                return name
    except Exception as error:
        logger.debug("Could not read project name from dbt_project.yml: %s", error)

    return None


def resolve_profiles_path(project_dir: Path) -> Path:
    """Resolve profiles.yml path from project dir with parent fallback."""
    project_profiles = project_dir / "profiles.yml"
    if project_profiles.exists():
        return project_profiles
    return project_dir.parent / "profiles.yml"


def load_artifact_config(project_dir: Path) -> Dict[str, Any]:
    """Load artifact storage configuration from ~/.dbt config file and env vars.

    Precedence (highest to lowest):
    1. Environment variables (XBT_LOOM_ARTIFACT_*)
    2. ~/.dbt/xbt_loom_artifacts.yml
    3. Default values
    """
    # Start with defaults
    default_artifacts_path = str(Path.home() / ".xbt" / "xbt_loom" / "artifacts")
    config: Dict[str, Any] = {
        "backend": "local",
        "local_path": default_artifacts_path,
        "bucket_name": None,
        "aws_region": "us-east-1",
        "stage_path": None,
        "upload_skip_patterns": [],
    }

    # Load from ~/.dbt/xbt_loom_artifacts.yml if it exists
    home_dir = Path.home()
    dbt_config_dir = home_dir / ".dbt"
    artifact_config_path = dbt_config_dir / "xbt_loom_artifacts.yml"

    if artifact_config_path.exists():
        try:
            with open(artifact_config_path, "r") as handle:
                file_config = yaml.safe_load(handle)
            if isinstance(file_config, dict):
                config.update(file_config)
        except Exception as error:
            logger.debug(
                "Could not load artifact config from %s: %s",
                artifact_config_path,
                error,
            )

    # Apply environment variable overrides (highest precedence)
    if env_backend := os.environ.get("XBT_LOOM_ARTIFACT_BACKEND"):
        config["backend"] = env_backend
    if env_local_path := os.environ.get("XBT_LOOM_ARTIFACT_LOCAL_PATH"):
        config["local_path"] = env_local_path
    if env_bucket := os.environ.get("XBT_LOOM_ARTIFACT_S3_BUCKET"):
        config["bucket_name"] = env_bucket
    if env_region := os.environ.get("XBT_LOOM_ARTIFACT_AWS_REGION"):
        config["aws_region"] = env_region
    if env_stage := os.environ.get("XBT_LOOM_ARTIFACT_SNOWFLAKE_STAGE"):
        config["stage_path"] = env_stage

    return config
