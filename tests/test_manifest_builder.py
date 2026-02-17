"""Tests for xbt_plugins.manifest_builder module."""

import pytest

from xbt_loom_plugin.manifest_builder import ManifestBuilder


class TestManifestBuilder:
    """Test ManifestBuilder class."""

    def test_build_file_manifest(self):
        """Test building file manifest entry."""
        entry = ManifestBuilder.build_manifest_entry(
            name="upstream",
            manifest_type="file",
            config={"path": "../upstream/target/manifest.json"},
        )

        assert entry["name"] == "upstream"
        assert entry["type"] == "file"
        assert entry["config"]["path"] == "../upstream/target/manifest.json"
        assert "excluded_packages" not in entry

    def test_build_s3_manifest(self):
        """Test building S3 manifest entry."""
        config = {
            "bucket_name": "my-bucket",
            "object_name": "manifests/project/manifest.json",
        }
        entry = ManifestBuilder.build_manifest_entry(
            name="upstream",
            manifest_type="s3",
            config=config,
        )

        assert entry["type"] == "s3"
        assert entry["config"]["bucket_name"] == "my-bucket"

    def test_build_manifest_with_excluded_packages(self):
        """Test building manifest with excluded packages."""
        entry = ManifestBuilder.build_manifest_entry(
            name="upstream",
            manifest_type="file",
            config={"path": "../upstream/target/manifest.json"},
            excluded_packages=["dbt_packages", "helper_pkg"],
        )

        assert entry["excluded_packages"] == ["dbt_packages", "helper_pkg"]

    def test_unsupported_manifest_type(self):
        """Test error on unsupported manifest type."""
        with pytest.raises(ValueError, match="Unsupported manifest type"):
            ManifestBuilder.build_manifest_entry(
                name="upstream",
                manifest_type="invalid_type",
                config={},
            )

    def test_supported_types_list(self):
        """Test SUPPORTED_TYPES contains all expected manifest types."""
        expected_types = [
            "file",
            "s3",
            "gcs",
            "azure",
            "dbt_cloud",
            "paradime",
            "snowflake",
            "databricks",
        ]

        for manifest_type in expected_types:
            assert manifest_type in ManifestBuilder.SUPPORTED_TYPES


class TestManifestValidation:
    """Test manifest configuration validation."""

    def test_validate_file_config_success(self):
        """Test valid file config passes validation."""
        config = {"path": "../upstream/target/manifest.json"}
        # Should not raise
        ManifestBuilder.validate_file_config(config)

    def test_validate_file_config_missing_path(self):
        """Test invalid file config missing path."""
        with pytest.raises(ValueError, match="'path'"):
            ManifestBuilder.validate_file_config({})

    def test_validate_s3_config_success(self):
        """Test valid S3 config passes validation."""
        config = {
            "bucket_name": "my-bucket",
            "object_name": "manifest.json",
        }
        ManifestBuilder.validate_s3_config(config)

    def test_validate_s3_config_missing_bucket(self):
        """Test invalid S3 config missing bucket."""
        with pytest.raises(ValueError, match="bucket_name"):
            ManifestBuilder.validate_s3_config({"object_name": "manifest.json"})

    def test_validate_gcs_config_success(self):
        """Test valid GCS config passes validation."""
        config = {
            "project_id": "my-project",
            "bucket_name": "my-bucket",
            "object_name": "manifest.json",
        }
        ManifestBuilder.validate_gcs_config(config)

    def test_validate_gcs_config_missing_fields(self):
        """Test invalid GCS config missing required fields."""
        with pytest.raises(ValueError, match="project_id"):
            ManifestBuilder.validate_gcs_config({})

    def test_validate_azure_config_success(self):
        """Test valid Azure config passes validation."""
        config = {
            "account_name": "myaccount",
            "container_name": "mycontainer",
            "object_name": "manifest.json",
        }
        ManifestBuilder.validate_azure_config(config)

    def test_validate_dbt_cloud_config_success(self):
        """Test valid dbt Cloud config passes validation."""
        config = {
            "account_id": "12345",
            "job_id": "67890",
        }
        ManifestBuilder.validate_dbt_cloud_config(config)

    def test_validate_config_dispatches_to_correct_validator(self):
        """Test validate_config dispatches to correct validator."""
        # File type
        config = {"path": "../upstream/target/manifest.json"}
        ManifestBuilder.validate_config("file", config)

        # S3 type
        config = {"bucket_name": "bucket", "object_name": "object"}
        ManifestBuilder.validate_config("s3", config)

    def test_validate_config_unknown_type_no_error(self):
        """Test validate_config for unknown type (no validation)."""
        # Should not raise
        ManifestBuilder.validate_config("paradime", {})
