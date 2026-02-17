"""Generate dbt_loom.config.yml from dependencies.yml and templates."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from .arg_parser import resolve_profiles_dir
from .manifest_builder import ManifestBuilder
from .template_engine import build_template_context, render_value

logger = logging.getLogger(__name__)


def read_yaml_file(file_path: Path) -> Dict[str, Any]:
    """
    Read and parse a YAML file.

    Args:
        file_path: Path to YAML file

    Returns:
        Parsed YAML content as dictionary

    Raises:
        FileNotFoundError: If file doesn't exist
        yaml.YAMLError: If file is not valid YAML
    """
    if not file_path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    with open(file_path, "r") as f:
        return yaml.safe_load(f) or {}


def read_dbt_project_yml(project_dir: Path) -> Dict[str, Any]:
    """
    Read dbt_project.yml and extract project name.

    Args:
        project_dir: Path to dbt project directory

    Returns:
        Parsed dbt_project.yml content

    Raises:
        FileNotFoundError: If dbt_project.yml not found
    """
    project_file = project_dir / "dbt_project.yml"
    return read_yaml_file(project_file)


def read_dependencies_yml(project_dir: Path) -> Optional[Dict[str, Any]]:
    """
    Read dependencies.yml if it exists.

    Args:
        project_dir: Path to dbt project directory

    Returns:
        Parsed dependencies.yml content or None if file doesn't exist
    """
    deps_file = project_dir / "dependencies.yml"
    if not deps_file.exists():
        return None

    try:
        return read_yaml_file(deps_file)
    except Exception as e:
        logger.warning(f"Failed to read dependencies.yml: {e}")
        return None


def extract_project_name(dbt_project: Dict[str, Any]) -> str:
    """
    Extract project name from dbt_project.yml.

    Args:
        dbt_project: Parsed dbt_project.yml content

    Returns:
        Project name

    Raises:
        ValueError: If 'name' field not found
    """
    name = dbt_project.get("name")
    if not name:
        raise ValueError("'name' field not found in dbt_project.yml")
    return name


def extract_dependencies(
    dependencies: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """
    Extract list of upstream projects from dependencies.yml.

    Supported formats:
    ```
    projects:
      - name: projectA
      - name: projectB
        type: s3
        config:
          bucket_name: my_bucket
          object_name: path/to/manifest.json
        excluded_packages:
          - dbt_project_evaluator
    ```

    Args:
        dependencies: Parsed dependencies.yml content

    Returns:
        List of dependency entries, empty list if none found
    """
    if not dependencies:
        return []

    projects = dependencies.get("projects", [])
    if not isinstance(projects, list):
        logger.warning("'projects' field in dependencies.yml is not a list")
        return []

    entries = []
    for proj in projects:
        if isinstance(proj, dict) and "name" in proj:
            entry = {
                "name": proj["name"],
                "type": proj.get("type", "file"),
                "config": proj.get("config"),
                "excluded_packages": proj.get("excluded_packages"),
            }
            entries.append(entry)
        else:
            logger.warning("Skipping invalid project entry: %s", proj)

    return entries


def load_template(project_dir: Path, workspace_root: Path) -> Optional[str]:
    """
    Load dbt_loom configuration template.

    Search order:
    1. {project_dir}/dbt_loom.config.template.yml
    2. {project_dir.parent}/dbt_loom.config.template.yml
    3. {workspace_root}/dbt_loom.config.template.yml

    Args:
        project_dir: Path to dbt project
        workspace_root: Path to workspace root

    Returns:
        Template content as string, or None if not found
    """
    # Try project-level template
    project_template = project_dir / "dbt_loom.config.template.yml"
    if project_template.exists():
        try:
            with open(project_template, "r") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read project template: {e}")

    # Try project parent template
    parent_template = project_dir.parent / "dbt_loom.config.template.yml"
    if parent_template.exists():
        try:
            with open(parent_template, "r") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read parent template: {e}")

    # Try workspace-level template
    workspace_template = workspace_root / "dbt_loom.config.template.yml"
    if workspace_template.exists():
        try:
            with open(workspace_template, "r") as f:
                return f.read()
        except Exception as e:
            logger.warning(f"Failed to read workspace template: {e}")

    return None


def get_default_config_yaml(manifests: List[Dict[str, Any]]) -> str:
    """
    Generate default dbt_loom.config.yml YAML structure.

    Args:
        manifests: List of manifest entries

    Returns:
        YAML string
    """
    config = {"manifests": manifests}
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _build_manifest_contexts(
    dependency_entries: List[Dict[str, Any]],
    project_dir: Path,
    profiles_dir: Optional[Path],
    project_name: str,
) -> List[Dict[str, Any]]:
    contexts = []
    for entry in dependency_entries:
        upstream_project = entry["name"]
        context = build_template_context(
            upstream_project=upstream_project,
            project_root=project_dir,
            profiles_dir=profiles_dir,
            project_name=project_name,
        )
        context.update(
            {
                "name": upstream_project,
                "manifest_type": entry.get("type", "file"),
                "config": entry.get("config") or {},
                "excluded_packages": entry.get("excluded_packages"),
            }
        )
        contexts.append(context)
    return contexts


def generate_config_for_project(
    project_dir: Path,
    args: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
) -> Optional[str]:
    """
    Generate dbt_loom.config.yml content for a project based on dependencies.yml.

    Args:
        project_dir: Path to dbt project directory
        args: Optional list of CLI arguments (for resolving profiles dir)
        workspace_root: Optional path to workspace root (for finding templates)

    Returns:
        Generated YAML content as string, or None if no dependencies found

    Raises:
        FileNotFoundError: If dbt_project.yml not found
        ValueError: If invalid configuration encountered
    """
    if args is None:
        args = []

    if workspace_root is None:
        workspace_root = Path.cwd()

    # Read project information
    dbt_project = read_dbt_project_yml(project_dir)
    project_name = extract_project_name(dbt_project)

    # Read dependencies
    dependencies = read_dependencies_yml(project_dir)
    dependency_entries = extract_dependencies(dependencies)

    if not dependency_entries:
        logger.debug(f"No dependencies found in {project_dir}")
        return None

    # Resolve profiles directory for template context
    profiles_dir = resolve_profiles_dir(args)

    # Load template if provided
    template_text = load_template(project_dir, workspace_root)
    manifest_contexts = _build_manifest_contexts(
        dependency_entries,
        project_dir,
        profiles_dir,
        project_name,
    )

    if template_text:
        project_context = {
            "project_name": project_name,
            "project_root": str(project_dir),
            "profiles_dir": str(profiles_dir) if profiles_dir else "",
            "upstream_projects": manifest_contexts,
        }
        return render_value(template_text, project_context)

    # Build manifest entries
    manifests = []
    for entry in dependency_entries:
        upstream_project = entry["name"]
        manifest_type = entry.get("type", "file")
        manifest_config = entry.get("config")
        excluded_packages = entry.get("excluded_packages")

        # Build template context
        context = build_template_context(
            upstream_project=upstream_project,
            project_root=project_dir,
            profiles_dir=profiles_dir,
            project_name=project_name,
        )
        context["manifest_type"] = manifest_type
        context["excluded_packages"] = excluded_packages

        if not manifest_config:
            if manifest_type != "file":
                logger.warning(
                    "Skipping %s due to missing config for manifest type %s",
                    upstream_project,
                    manifest_type,
                )
                continue
            manifest_config = {"path": context["manifest_path"]}

        rendered_config = {
            key: render_value(value, context) for key, value in manifest_config.items()
        }

        ManifestBuilder.validate_config(manifest_type, rendered_config)

        manifest_entry = ManifestBuilder.build_manifest_entry(
            name=upstream_project,
            manifest_type=manifest_type,
            config=rendered_config,
            excluded_packages=excluded_packages,
        )

        manifests.append(manifest_entry)

    # Generate YAML
    return get_default_config_yaml(manifests)


def write_config_file(project_dir: Path, config_yaml: str) -> Path:
    """
    Write generated configuration to dbt_loom.config.yml.

    Args:
        project_dir: Path to dbt project directory
        config_yaml: YAML content to write

    Returns:
        Path to written file

    Raises:
        IOError: If file write fails
    """
    config_file = project_dir / "dbt_loom.config.yml"

    with open(config_file, "w") as f:
        f.write(config_yaml)

    logger.info(f"Generated dbt_loom.config.yml at {config_file}")
    return config_file


def auto_configure_loom(
    project_dir: Path,
    args: Optional[List[str]] = None,
    workspace_root: Optional[Path] = None,
) -> Optional[Path]:
    """
    Automatically generate dbt_loom.config.yml if dependencies.yml exists.

    This is the main entry point for the configuration generation.

    Args:
        project_dir: Path to dbt project directory
        args: Optional list of CLI arguments
        workspace_root: Optional path to workspace root

    Returns:
        Path to generated config file, or None if no dependencies found

    Raises:
        FileNotFoundError: If dbt_project.yml not found
    """
    if not (project_dir / "dbt_project.yml").exists():
        logger.debug(f"No dbt_project.yml found in {project_dir}, skipping")
        return None

    config_yaml = generate_config_for_project(
        project_dir, args=args, workspace_root=workspace_root
    )

    if not config_yaml:
        logger.debug(f"No configuration generated for {project_dir}")
        return None

    return write_config_file(project_dir, config_yaml)
