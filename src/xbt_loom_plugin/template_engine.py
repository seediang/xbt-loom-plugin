"""Template engine for rendering configuration with environment variables and Jinja2."""

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


def render_value(value: Any, context: Optional[Dict[str, Any]] = None) -> str:
    """
    Render a value through Jinja2 templating and environment variable substitution.

    Process order:
    1. Apply Jinja2 templating with provided context
    2. Substitute environment variables (${VAR} and $VAR formats)

    Args:
        value: String value to render (will be converted to string if not)
        context: Optional Jinja2 context dictionary

    Returns:
        Rendered string value
    """
    if context is None:
        context = {}

    # Convert to string
    text = str(value)

    # Step 1: Apply Jinja2 template rendering
    text = render_jinja2(text, context)

    # Step 2: Substitute environment variables
    text = substitute_env_vars(text)

    return text


def render_jinja2(template_text: str, context: Dict[str, Any]) -> str:
    """
    Render Jinja2 template using provided context.

    Uses a minimal safe implementation without unsafe features.

    Args:
        template_text: Template string with {{ variable }} syntax
        context: Dictionary of variables available to template

    Returns:
        Rendered string
    """
    try:
        from jinja2 import Environment, StrictUndefined

        env = Environment(undefined=StrictUndefined)
        template = env.from_string(template_text)
        return template.render(**context)
    except Exception as e:
        logger.warning("Jinja2 rendering failed: %s", e)
        return template_text


def substitute_env_vars(text: str) -> str:
    """
    Substitute environment variables in text.

    Supports two formats:
    - ${VAR_NAME}: Explicit braces
    - $VAR_NAME: Dollar followed by identifier

    Unknown variables are left unchanged.

    Args:
        text: String with environment variable placeholders

    Returns:
        String with environment variables substituted
    """
    # Pattern 1: ${VAR_NAME}
    def replace_braced(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    text = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace_braced, text)

    # Pattern 2: $VAR_NAME (only if not already matched by pattern 1)
    def replace_unbraced(match):
        var_name = match.group(1)
        return os.getenv(var_name, match.group(0))

    text = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)", replace_unbraced, text)

    return text


def build_template_context(
    upstream_project: str,
    project_root: Path,
    profiles_dir: Optional[Path] = None,
    project_name: Optional[str] = None,
    manifest_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Build context dictionary for Jinja2 template rendering.

    Args:
        upstream_project: Name of upstream project (from dependencies.yml)
        project_root: Root directory of current dbt project
        profiles_dir: Path to profiles directory (optional)
        project_name: Name of current project (from dbt_project.yml)
        manifest_path: Optional pre-computed manifest path

    Returns:
        Dictionary with template context variables
    """
    context = {
        "upstream_project": upstream_project,
        "project_root": str(project_root),
        "project_name": project_name or "",
    }

    if profiles_dir:
        context["profiles_dir"] = str(profiles_dir)

    # Compute manifest path if not provided
    relative_path = f"../{upstream_project}/target/manifest.json"
    if manifest_path:
        context["manifest_path"] = manifest_path
    else:
        context["manifest_path"] = relative_path

    context["manifest_path_abs"] = str(
        (project_root.parent / upstream_project / "target" / "manifest.json").resolve()
    )

    return context
