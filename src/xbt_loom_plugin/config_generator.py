"""Generate dbt_loom.config.yml from dependencies.yml and templates."""

import logging
from pathlib import Path
from typing import Any

import yaml

from .arg_parser import resolve_profiles_dir
from .manifest_builder import ManifestBuilder
from .template_engine import build_template_context, render_nested, render_value
from .types import DependencyEntry, ManifestConfig, ManifestEntry, TemplateContext
from .utils import get_template_candidates, read_text_file, read_yaml_file

logger = logging.getLogger(__name__)


def read_dbt_project_yml(project_dir: Path) -> dict[str, Any]:
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


def read_dependencies_yml(project_dir: Path) -> dict[str, Any] | None:
    """
    Read dependencies.yml if it exists.

    Args:
        project_dir: Path to dbt project directory

    Returns:
        Parsed dependencies.yml content or None if file doesn't exist

    Raises:
        ValueError: If dependencies.yml is not a mapping
    """
    deps_file = project_dir / "dependencies.yml"
    if not deps_file.exists():
        return None

    dependencies = read_yaml_file(deps_file)
    if dependencies is None:
        return {}
    if not isinstance(dependencies, dict):
        raise ValueError("dependencies.yml must contain a top-level mapping")
    return dependencies


def extract_project_name(dbt_project: dict[str, Any]) -> str:
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


def extract_dependencies(dependencies: dict[str, Any] | None) -> list[DependencyEntry]:
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

    Raises:
        ValueError: If projects shape or project entry fields are invalid
    """
    if not dependencies:
        return []

    projects = dependencies.get("projects", [])
    if not isinstance(projects, list):
        raise ValueError("'projects' field in dependencies.yml must be a list")

    entries: list[DependencyEntry] = []
    for index, proj in enumerate(projects):
        if not isinstance(proj, dict):
            raise ValueError(
                f"Invalid project entry at index {index}: expected mapping, got {type(proj).__name__}"
            )

        name = proj.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Invalid project entry at index {index}: 'name' must be a non-empty string"
            )

        manifest_type = proj.get("type", "file")
        if not isinstance(manifest_type, str) or not manifest_type.strip():
            raise ValueError(
                f"Invalid project entry '{name}': 'type' must be a non-empty string"
            )

        config = proj.get("config")
        if config is not None and not isinstance(config, dict):
            raise ValueError(
                f"Invalid project entry '{name}': 'config' must be a mapping"
            )

        excluded_packages = proj.get("excluded_packages")
        if excluded_packages is not None:
            if not isinstance(excluded_packages, list) or not all(
                isinstance(item, str) for item in excluded_packages
            ):
                raise ValueError(
                    f"Invalid project entry '{name}': 'excluded_packages' must be a list of strings"
                )

        entry: DependencyEntry = {
            "name": name,
            "type": manifest_type,
            "config": config,
            "excluded_packages": excluded_packages,
        }
        entries.append(entry)

    return entries


def load_template(project_dir: Path, workspace_root: Path) -> str | None:
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
    for template_path in get_template_candidates(project_dir, workspace_root):
        if not template_path.exists():
            continue
        try:
            return read_text_file(template_path)
        except Exception as e:
            logger.warning("Failed to read template %s: %s", template_path, e)

    return None


def get_default_config_yaml(manifests: list[ManifestEntry]) -> str:
    """
    Generate default dbt_loom.config.yml YAML structure.

    Args:
        manifests: List of manifest entries

    Returns:
        YAML string
    """
    config = {"manifests": manifests}
    return yaml.dump(config, default_flow_style=False, sort_keys=False)


def _build_manifest_context(
    entry: DependencyEntry,
    project_dir: Path,
    profiles_dir: Path | None,
    project_name: str,
) -> TemplateContext:
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
    return context


def _build_manifest_contexts(
    dependency_entries: list[DependencyEntry],
    project_dir: Path,
    profiles_dir: Path | None,
    project_name: str,
) -> list[TemplateContext]:
    return [
        _build_manifest_context(entry, project_dir, profiles_dir, project_name)
        for entry in dependency_entries
    ]


def _validate_template_config(config_yaml: str) -> None:
    parsed = yaml.safe_load(config_yaml) or {}
    if not isinstance(parsed, dict):
        raise ValueError("Template output must be a YAML mapping")

    manifests = parsed.get("manifests")
    if manifests is None:
        raise ValueError("Template output must include top-level 'manifests'")

    if not isinstance(manifests, list):
        raise ValueError("Template output field 'manifests' must be a list")

    for index, manifest in enumerate(manifests):
        if not isinstance(manifest, dict):
            raise ValueError(f"Template manifest at index {index} must be a mapping")

        name = manifest.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(
                f"Template manifest at index {index} must include a non-empty 'name'"
            )

        manifest_type = manifest.get("type")
        if not isinstance(manifest_type, str) or not manifest_type.strip():
            raise ValueError(
                f"Template manifest '{name}' must include a non-empty 'type'"
            )

        config = manifest.get("config")
        if not isinstance(config, dict):
            raise ValueError(
                f"Template manifest '{name}' must include a mapping 'config'"
            )

        ManifestBuilder.build_manifest_entry(
            name=name,
            manifest_type=manifest_type,
            config=config,
            excluded_packages=manifest.get("excluded_packages"),
        )
        ManifestBuilder.validate_config(manifest_type, config)


def _render_template_config(
    template_text: str,
    project_name: str,
    project_dir: Path,
    profiles_dir: Path | None,
    manifest_contexts: list[TemplateContext],
) -> str:
    project_context = {
        "project_name": project_name,
        "project_root": str(project_dir),
        "profiles_dir": str(profiles_dir) if profiles_dir else "",
        "upstream_projects": manifest_contexts,
    }
    rendered = render_value(template_text, project_context)
    _validate_template_config(rendered)
    return rendered


def _build_manifest_entries(
    dependency_entries: list[DependencyEntry],
    project_dir: Path,
    profiles_dir: Path | None,
    project_name: str,
) -> list[ManifestEntry]:
    manifests: list[ManifestEntry] = []
    for entry in dependency_entries:
        upstream_project = entry["name"]
        manifest_type = entry.get("type", "file")
        manifest_config: ManifestConfig | None = entry.get("config")
        excluded_packages = entry.get("excluded_packages")

        context = _build_manifest_context(
            entry,
            project_dir,
            profiles_dir,
            project_name,
        )

        if not manifest_config:
            if manifest_type != "file":
                raise ValueError(
                    f"Missing 'config' for manifest '{upstream_project}' of type '{manifest_type}'"
                )
            manifest_config = {"path": context["manifest_path"]}

        rendered_config = render_nested(manifest_config, context)

        ManifestBuilder.validate_config(manifest_type, rendered_config)

        manifest_entry = ManifestBuilder.build_manifest_entry(
            name=upstream_project,
            manifest_type=manifest_type,
            config=rendered_config,
            excluded_packages=excluded_packages,
        )

        manifests.append(manifest_entry)

    return manifests


def generate_config_for_project(
    project_dir: Path,
    args: list[str] | None = None,
    workspace_root: Path | None = None,
) -> str | None:
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
        ValueError: If dependencies or rendered manifest configuration is invalid
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
        return _render_template_config(
            template_text,
            project_name,
            project_dir,
            profiles_dir,
            manifest_contexts,
        )

    manifests = _build_manifest_entries(
        dependency_entries,
        project_dir,
        profiles_dir,
        project_name,
    )
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
    args: list[str] | None = None,
    workspace_root: Path | None = None,
) -> Path | None:
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
