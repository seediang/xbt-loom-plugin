"""Tests for artifact storage module."""

import gzip
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from xbt_loom_plugin.artifact_storage import (
    LocalArtifactStorage,
    S3ArtifactStorage,
    SnowflakeArtifactStorage,
    get_artifact_storage,
    should_skip_upload,
)


class TestLocalArtifactStorage:
    """Test LocalArtifactStorage implementation."""

    @pytest.fixture
    def temp_storage_dir(self):
        """Create temporary directory for storage."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield tmpdir

    @pytest.fixture
    def temp_artifacts(self):
        """Create temporary artifact files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create manifest.json
            manifest = {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/manifest/v11.json"
                },
                "nodes": {},
            }
            manifest_path = tmpdir_path / "manifest.json"
            manifest_path.write_text(json.dumps(manifest))

            # Create run_results.json
            run_results = {
                "metadata": {
                    "dbt_schema_version": "https://schemas.getdbt.com/dbt/run-results/v5.json"
                },
                "results": [],
            }
            run_results_path = tmpdir_path / "run_results.json"
            run_results_path.write_text(json.dumps(run_results))

            yield str(manifest_path), str(run_results_path)

    def test_upload_creates_versioned_folder(self, temp_storage_dir, temp_artifacts):
        """Test that upload creates timestamped version folder."""
        storage = LocalArtifactStorage("dev", "projectA", temp_storage_dir)
        manifest_path, run_results_path = temp_artifacts

        result = storage.upload(manifest_path, run_results_path)

        assert result is True

        # Verify folder structure
        project_dir = Path(temp_storage_dir) / "dev" / "projectA"
        assert project_dir.exists()

        # Check timestamped folder exists
        version_folders = [
            d for d in project_dir.iterdir() if d.is_dir() and d.name != "latest"
        ]
        assert len(version_folders) == 1

        # Check latest folder
        latest_dir = project_dir / "latest"
        assert latest_dir.exists()
        assert (latest_dir / "manifest.json.gz").exists()
        assert (latest_dir / "run_results.json.gz").exists()

    def test_upload_gzips_files(self, temp_storage_dir, temp_artifacts):
        """Test that upload gzips artifact files."""
        storage = LocalArtifactStorage("dev", "projectA", temp_storage_dir)
        manifest_path, run_results_path = temp_artifacts

        storage.upload(manifest_path, run_results_path)

        latest_dir = Path(temp_storage_dir) / "dev" / "projectA" / "latest"

        # Verify files are gzipped
        manifest_gz = latest_dir / "manifest.json.gz"
        run_results_gz = latest_dir / "run_results.json.gz"

        assert manifest_gz.exists()
        assert run_results_gz.exists()

        # Verify can decompress
        with gzip.open(manifest_gz, "rb") as f:
            manifest_data = json.loads(f.read().decode())
            assert "metadata" in manifest_data

    def test_download_latest_version(self, temp_storage_dir, temp_artifacts):
        """Test downloading latest version of artifacts."""
        storage = LocalArtifactStorage("dev", "projectA", temp_storage_dir)
        manifest_path, run_results_path = temp_artifacts

        # Upload first
        storage.upload(manifest_path, run_results_path)

        # Download (keep temp_dir outside the with block)
        with tempfile.TemporaryDirectory() as download_dir:
            result = storage.download(version=None, temp_dir=download_dir)

            assert "manifest_path" in result
            assert "run_results_path" in result

            # Verify files are accessible
            manifest_file = Path(result["manifest_path"])
            run_results_file = Path(result["run_results_path"])

            assert manifest_file.exists()
            assert run_results_file.exists()

            # Verify content (while temp_dir still exists)
            manifest_data = json.loads(manifest_file.read_text())
            assert "metadata" in manifest_data

    def test_download_specific_version(self, temp_storage_dir, temp_artifacts):
        """Test downloading specific version of artifacts."""
        storage = LocalArtifactStorage("dev", "projectA", temp_storage_dir)
        manifest_path, run_results_path = temp_artifacts

        # Upload first
        storage.upload(manifest_path, run_results_path)

        # Get version timestamp
        project_dir = Path(temp_storage_dir) / "dev" / "projectA"
        version_folders = [
            d for d in project_dir.iterdir() if d.is_dir() and d.name != "latest"
        ]
        version_timestamp = version_folders[0].name

        # Download specific version
        with tempfile.TemporaryDirectory() as download_dir:
            result = storage.download(version=version_timestamp, temp_dir=download_dir)

        assert "manifest_path" in result
        assert "run_results_path" in result

    def test_download_nonexistent_project(self, temp_storage_dir):
        """Test downloading nonexistent project returns empty dict."""
        storage = LocalArtifactStorage("dev", "nonexistent", temp_storage_dir)

        result = storage.download()

        assert result == {}

    def test_list_versions(self, temp_storage_dir, temp_artifacts):
        """Test listing available versions."""
        storage = LocalArtifactStorage("dev", "projectA", temp_storage_dir)
        manifest_path, run_results_path = temp_artifacts

        # Upload multiple times
        storage.upload(manifest_path, run_results_path)

        versions = storage.list_versions()

        assert len(versions) == 1
        assert versions[0]  # Should have a timestamp

    def test_list_versions_empty(self, temp_storage_dir):
        """Test listing versions for nonexistent project."""
        storage = LocalArtifactStorage("dev", "nonexistent", temp_storage_dir)

        versions = storage.list_versions()

        assert versions == []


class TestSkipPatterns:
    """Test skip pattern matching."""

    def test_exact_match(self):
        """Test exact match skip pattern."""
        assert should_skip_upload("dev", ["dev"]) is True
        assert should_skip_upload("dev", ["prod"]) is False

    def test_regex_match(self):
        """Test regex pattern matching."""
        assert should_skip_upload("dev", ["dev.*"]) is True
        assert should_skip_upload("dev123", ["dev.*"]) is True
        assert should_skip_upload("prod", ["dev.*"]) is False

    def test_regex_anchors(self):
        """Test regex with anchors."""
        assert should_skip_upload("dev", ["^dev$"]) is True
        assert should_skip_upload("dev_", ["^dev$"]) is False

    def test_multiple_patterns(self):
        """Test multiple skip patterns."""
        patterns = ["dev", "test.*", "^local$"]

        assert should_skip_upload("dev", patterns) is True
        assert should_skip_upload("test123", patterns) is True
        assert should_skip_upload("local", patterns) is True
        assert should_skip_upload("prod", patterns) is False

    def test_empty_patterns(self):
        """Test with empty skip patterns list."""
        assert should_skip_upload("dev", []) is False
        assert should_skip_upload("dev", None) is False


class TestGetArtifactStorage:
    """Test artifact storage factory method."""

    def test_local_backend(self):
        """Test creating local storage backend."""
        storage = get_artifact_storage(
            "local",
            "dev",
            "projectA",
            {"local_path": "/tmp/artifacts"},
        )

        assert isinstance(storage, LocalArtifactStorage)

    def test_s3_backend(self):
        """Test creating S3 storage backend."""
        storage = get_artifact_storage(
            "s3",
            "dev",
            "projectA",
            {
                "bucket_name": "my-bucket",
                "aws_region": "us-west-2",
            },
        )

        assert isinstance(storage, S3ArtifactStorage)

    def test_s3_backend_missing_bucket(self):
        """Test S3 backend fails without bucket name."""
        storage = get_artifact_storage(
            "s3",
            "dev",
            "projectA",
            {},
        )

        assert storage is None

    def test_snowflake_backend(self):
        """Test creating Snowflake storage backend."""
        storage = get_artifact_storage(
            "snowflake",
            "dev",
            "projectA",
            {"stage_path": "@my_stage"},
        )

        assert isinstance(storage, SnowflakeArtifactStorage)

    def test_snowflake_backend_missing_stage(self):
        """Test Snowflake backend fails without stage path."""
        storage = get_artifact_storage(
            "snowflake",
            "dev",
            "projectA",
            {},
        )

        assert storage is None

    def test_unknown_backend(self):
        """Test unknown backend returns None."""
        storage = get_artifact_storage(
            "unknown",
            "dev",
            "projectA",
            {},
        )

        assert storage is None


class TestS3ArtifactStorage:
    """Test S3ArtifactStorage implementation."""

    @patch("xbt_loom_plugin.artifact_storage.boto3.client")
    def test_s3_upload_success(self, mock_boto_client):
        """Test successful S3 upload."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        storage = S3ArtifactStorage("dev", "projectA", "my-bucket")

        # Create temp files
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            manifest_path = tmpdir_path / "manifest.json"
            manifest_path.write_text(json.dumps({"test": "manifest"}))

            run_results_path = tmpdir_path / "run_results.json"
            run_results_path.write_text(json.dumps({"test": "results"}))

            result = storage.upload(str(manifest_path), str(run_results_path))

        assert result is True
        assert (
            mock_client.put_object.call_count == 4
        )  # 2 files × 2 locations (versioned + latest)

    @patch("xbt_loom_plugin.artifact_storage.boto3.client")
    def test_s3_download_success(self, mock_boto_client):
        """Test successful S3 download."""
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client

        # Mock gzipped data
        manifest_data = gzip.compress(json.dumps({"test": "manifest"}).encode())
        run_results_data = gzip.compress(json.dumps({"test": "results"}).encode())

        mock_client.get_object.side_effect = [
            {"Body": MagicMock(read=lambda: manifest_data)},
            {"Body": MagicMock(read=lambda: run_results_data)},
        ]

        storage = S3ArtifactStorage("dev", "projectA", "my-bucket")

        with tempfile.TemporaryDirectory() as tmpdir:
            result = storage.download(version=None, temp_dir=tmpdir)

        assert "manifest_path" in result
        assert "run_results_path" in result
