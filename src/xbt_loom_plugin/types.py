"""Shared type definitions for xbt loom plugin modules."""

from typing import Any, TypedDict

ManifestConfig = dict[str, Any]
TemplateContext = dict[str, Any]
ArtifactResult = dict[str, str]


class ParsedCliArgs(TypedDict):
    """Parsed dbt CLI directory flags."""

    project_dir: str | None
    profiles_dir: str | None


class DependencyEntry(TypedDict):
    """Normalized dependency entry parsed from dependencies.yml."""

    name: str
    type: str
    config: ManifestConfig | None
    excluded_packages: list[str] | None


class ManifestEntry(TypedDict, total=False):
    """dbt-loom manifest entry shape."""

    name: str
    type: str
    config: ManifestConfig
    excluded_packages: list[str]
