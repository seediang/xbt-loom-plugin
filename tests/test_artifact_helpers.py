"""Tests for shared artifact helper functions."""

import yaml

from xbt_loom_plugin.artifact_helpers import (
    extract_dbt_target,
    get_project_name,
    load_artifact_config,
    resolve_profiles_path,
)


class TestExtractDbtTarget:
    """Target resolution helpers."""

    def test_extract_target_from_flag_value(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text(yaml.dump({"default": {"outputs": {"dev": {}}}}))

        assert extract_dbt_target(["--target", "prod"], profiles) == "prod"

    def test_extract_target_from_flag_equals(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text(yaml.dump({"default": {"outputs": {"dev": {}}}}))

        assert extract_dbt_target(["--target=qa"], profiles) == "qa"

    def test_extract_target_from_profiles_default(self, tmp_path):
        profiles = tmp_path / "profiles.yml"
        profiles.write_text(
            yaml.dump(
                {
                    "default": {
                        "outputs": {
                            "dev": {"type": "duckdb"},
                            "prod": {"type": "duckdb"},
                        }
                    }
                }
            )
        )

        assert extract_dbt_target([], profiles) == "dev"


class TestProjectAndConfigHelpers:
    """Project name and artifact config helpers."""

    def test_get_project_name(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectA"}))

        assert get_project_name(project_dir) == "projectA"

    def test_resolve_profiles_path_prefers_project(self, tmp_path):
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        project_profiles = project_dir / "profiles.yml"
        project_profiles.write_text("project: {}\n")

        assert resolve_profiles_path(project_dir) == project_profiles

    def test_load_artifact_config_defaults(self, tmp_path, monkeypatch):
        """Test that defaults are returned when no config file or env vars exist."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Set HOME to tmp_path to ensure no ~/.dbt config exists
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("XBT_LOOM_ARTIFACT_BACKEND", raising=False)
        monkeypatch.delenv("XBT_LOOM_ARTIFACT_LOCAL_PATH", raising=False)
        monkeypatch.delenv("XBT_LOOM_ARTIFACT_S3_BUCKET", raising=False)

        config = load_artifact_config(project_dir)

        expected_path = str(tmp_path / ".xbt" / "xbt_loom" / "artifacts")
        assert config["backend"] == "local"
        assert config["local_path"] == expected_path
        assert config["bucket_name"] is None
        assert config["aws_region"] == "us-east-1"
        assert config["stage_path"] is None
        assert config["upload_skip_patterns"] == []

    def test_load_artifact_config_from_dbt_dir(self, tmp_path, monkeypatch):
        """Test loading config from ~/.dbt/xbt_loom_artifacts.yml."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create ~/.dbt/xbt_loom_artifacts.yml
        dbt_dir = tmp_path / ".dbt"
        dbt_dir.mkdir()
        config_file = dbt_dir / "xbt_loom_artifacts.yml"
        config_file.write_text(
            yaml.dump(
                {
                    "backend": "s3",
                    "bucket_name": "my-bucket",
                    "upload_skip_patterns": ["dev", "test"],
                }
            )
        )

        # Point HOME to tmp_path
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.delenv("XBT_LOOM_ARTIFACT_BACKEND", raising=False)

        config = load_artifact_config(project_dir)

        assert config["backend"] == "s3"
        assert config["bucket_name"] == "my-bucket"
        assert config["upload_skip_patterns"] == ["dev", "test"]
        assert config["aws_region"] == "us-east-1"  # Default preserved

    def test_load_artifact_config_env_overrides(self, tmp_path, monkeypatch):
        """Test that env vars override config file settings."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        # Create config file with some settings
        dbt_dir = tmp_path / ".dbt"
        dbt_dir.mkdir()
        config_file = dbt_dir / "xbt_loom_artifacts.yml"
        config_file.write_text(
            yaml.dump(
                {
                    "backend": "s3",
                    "bucket_name": "file-bucket",
                    "aws_region": "us-west-2",
                }
            )
        )

        # Set env vars that should override
        monkeypatch.setenv("HOME", str(tmp_path))
        monkeypatch.setenv("XBT_LOOM_ARTIFACT_BACKEND", "snowflake")
        monkeypatch.setenv("XBT_LOOM_ARTIFACT_SNOWFLAKE_STAGE", "@my_stage/artifacts")

        config = load_artifact_config(project_dir)

        assert config["backend"] == "snowflake"  # Env override
        assert config["bucket_name"] == "file-bucket"  # From file
        assert config["aws_region"] == "us-west-2"  # From file
        assert config["stage_path"] == "@my_stage/artifacts"  # Env override
