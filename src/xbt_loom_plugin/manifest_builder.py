"""Build dbt-loom manifest entries from templates and configuration."""

from typing import Any, Dict, List, Optional


class ManifestBuilder:
    """Builds manifest entries for dbt-loom configuration."""

    SUPPORTED_TYPES = [
        "file",
        "s3",
        "gcs",
        "azure",
        "dbt_cloud",
        "paradime",
        "snowflake",
        "databricks",
    ]

    @staticmethod
    def build_manifest_entry(
        name: str,
        manifest_type: str,
        config: Dict[str, Any],
        excluded_packages: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """
        Build a manifest entry following dbt-loom structure.

        Args:
            name: Project name (must match dbt_project.yml name)
            manifest_type: Type of manifest source (file, s3, gcs, etc.)
            config: Configuration dictionary for the manifest type
            excluded_packages: Optional list of packages to exclude

        Returns:
            Dictionary representing a manifest entry

        Raises:
            ValueError: If manifest_type is not supported
        """
        if manifest_type not in ManifestBuilder.SUPPORTED_TYPES:
            raise ValueError(
                f"Unsupported manifest type: {manifest_type}. "
                f"Supported types: {', '.join(ManifestBuilder.SUPPORTED_TYPES)}"
            )

        entry = {
            "name": name,
            "type": manifest_type,
            "config": config,
        }

        if excluded_packages:
            entry["excluded_packages"] = excluded_packages

        return entry

    @staticmethod
    def validate_file_config(config: Dict[str, Any]) -> None:
        """Validate file manifest type config."""
        if "path" not in config:
            raise ValueError("File manifest requires 'path' in config")

    @staticmethod
    def validate_s3_config(config: Dict[str, Any]) -> None:
        """Validate S3 manifest type config."""
        required = ["bucket_name", "object_name"]
        for key in required:
            if key not in config:
                raise ValueError(f"S3 manifest requires '{key}' in config")

    @staticmethod
    def validate_gcs_config(config: Dict[str, Any]) -> None:
        """Validate GCS manifest type config."""
        required = ["project_id", "bucket_name", "object_name"]
        for key in required:
            if key not in config:
                raise ValueError(f"GCS manifest requires '{key}' in config")

    @staticmethod
    def validate_azure_config(config: Dict[str, Any]) -> None:
        """Validate Azure manifest type config."""
        required = ["account_name", "container_name", "object_name"]
        for key in required:
            if key not in config:
                raise ValueError(f"Azure manifest requires '{key}' in config")

    @staticmethod
    def validate_dbt_cloud_config(config: Dict[str, Any]) -> None:
        """Validate dbt Cloud manifest type config."""
        required = ["account_id", "job_id"]
        for key in required:
            if key not in config:
                raise ValueError(f"dbt Cloud manifest requires '{key}' in config")

    @staticmethod
    def validate_config(manifest_type: str, config: Dict[str, Any]) -> None:
        """
        Validate configuration for a manifest type.

        Args:
            manifest_type: Type of manifest
            config: Configuration dictionary

        Raises:
            ValueError: If required fields are missing
        """
        validators = {
            "file": ManifestBuilder.validate_file_config,
            "s3": ManifestBuilder.validate_s3_config,
            "gcs": ManifestBuilder.validate_gcs_config,
            "azure": ManifestBuilder.validate_azure_config,
            "dbt_cloud": ManifestBuilder.validate_dbt_cloud_config,
        }

        validator = validators.get(manifest_type)
        if validator:
            validator(config)
