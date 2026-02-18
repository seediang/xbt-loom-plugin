"""Tests for artifact CLI commands."""

import argparse
from pathlib import Path
from unittest.mock import MagicMock, patch

from xbt_loom_plugin.artifacts_cli import (
    _get_project_dir,
    list_artifacts,
    main,
    pull_artifacts,
    push_artifacts,
)


class TestGetProjectDir:
    """Tests for _get_project_dir() helper."""

    @patch("xbt_loom_plugin.artifacts_cli.resolve_project_dir")
    def test_returns_resolved_project_dir(self, mock_resolve, tmp_path):
        project = tmp_path / "project"
        project.mkdir()
        mock_resolve.return_value = project

        result = _get_project_dir()
        assert result == project
        mock_resolve.assert_called_once_with([])

    @patch("xbt_loom_plugin.artifacts_cli.resolve_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.Path.cwd")
    def test_checks_parent_for_dbt_project(self, mock_cwd, mock_resolve, tmp_path):
        mock_resolve.return_value = None

        parent = tmp_path / "parent"
        parent.mkdir()
        (parent / "dbt_project.yml").touch()

        cwd = parent / "subdir"
        cwd.mkdir()
        mock_cwd.return_value = cwd

        result = _get_project_dir()
        assert result == parent

    @patch("xbt_loom_plugin.artifacts_cli.resolve_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.Path.cwd")
    def test_checks_subdirectories_for_dbt_project(
        self, mock_cwd, mock_resolve, tmp_path
    ):
        mock_resolve.return_value = None

        cwd = tmp_path / "workspace"
        cwd.mkdir()
        mock_cwd.return_value = cwd

        # Create a subdir with dbt_project.yml
        project = cwd / "projectA"
        project.mkdir()
        (project / "dbt_project.yml").touch()

        # Create another subdir without it
        (cwd / "other").mkdir()

        result = _get_project_dir()
        assert result == project

    @patch("xbt_loom_plugin.artifacts_cli.resolve_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.Path.cwd")
    def test_returns_none_when_no_project_found(self, mock_cwd, mock_resolve, tmp_path):
        mock_resolve.return_value = None
        cwd = tmp_path / "empty"
        cwd.mkdir()
        mock_cwd.return_value = cwd

        result = _get_project_dir()
        assert result is None


class TestPushArtifacts:
    """Tests for push_artifacts() command."""

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    def test_returns_error_when_no_project_dir(self, mock_get_project):
        mock_get_project.return_value = None
        args = argparse.Namespace(target=None, force=False)

        result = push_artifacts(args)
        assert result == 1

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.get_project_name")
    def test_returns_error_when_no_project_name(
        self, mock_get_name, mock_get_project, tmp_path
    ):
        project = tmp_path / "project"
        project.mkdir()
        mock_get_project.return_value = project
        mock_get_name.return_value = None

        args = argparse.Namespace(target=None, force=False)
        result = push_artifacts(args)
        assert result == 1

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.get_project_name")
    def test_returns_error_when_artifacts_not_found(
        self, mock_get_name, mock_get_project, tmp_path
    ):
        project = tmp_path / "project"
        project.mkdir()
        (project / "target").mkdir()

        mock_get_project.return_value = project
        mock_get_name.return_value = "projectA"

        args = argparse.Namespace(target=None, force=False)
        result = push_artifacts(args)
        assert result == 1

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.get_project_name")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.should_skip_upload")
    def test_skips_upload_when_pattern_matches(
        self,
        mock_should_skip,
        mock_load_config,
        mock_extract_target,
        mock_resolve_profiles,
        mock_get_name,
        mock_get_project,
        tmp_path,
    ):
        project = tmp_path / "project"
        project.mkdir()
        target_dir = project / "target"
        target_dir.mkdir()
        (target_dir / "manifest.json").touch()
        (target_dir / "run_results.json").touch()

        mock_get_project.return_value = project
        mock_get_name.return_value = "projectA"
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"
        mock_load_config.return_value = {
            "backend": "local",
            "upload_skip_patterns": ["dev"],
        }
        mock_should_skip.return_value = True

        args = argparse.Namespace(target=None, force=False)
        result = push_artifacts(args)

        assert result == 0
        mock_should_skip.assert_called_once_with("dev", ["dev"])

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.get_project_name")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.should_skip_upload")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_uploads_successfully(
        self,
        mock_get_storage,
        mock_should_skip,
        mock_load_config,
        mock_extract_target,
        mock_resolve_profiles,
        mock_get_name,
        mock_get_project,
        tmp_path,
        capsys,
    ):
        project = tmp_path / "project"
        project.mkdir()
        target_dir = project / "target"
        target_dir.mkdir()
        (target_dir / "manifest.json").touch()
        (target_dir / "run_results.json").touch()

        mock_get_project.return_value = project
        mock_get_name.return_value = "projectA"
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "prod"
        mock_load_config.return_value = {"backend": "s3"}
        mock_should_skip.return_value = False

        mock_storage = MagicMock()
        mock_storage.upload.return_value = True
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(target=None, force=False)
        result = push_artifacts(args)

        assert result == 0
        mock_storage.upload.assert_called_once()

        captured = capsys.readouterr()
        assert "Successfully uploaded" in captured.out

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.get_project_name")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.should_skip_upload")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_force_flag_bypasses_skip_patterns(
        self,
        mock_get_storage,
        mock_should_skip,
        mock_load_config,
        mock_extract_target,
        mock_resolve_profiles,
        mock_get_name,
        mock_get_project,
        tmp_path,
    ):
        project = tmp_path / "project"
        project.mkdir()
        target_dir = project / "target"
        target_dir.mkdir()
        (target_dir / "manifest.json").touch()
        (target_dir / "run_results.json").touch()

        mock_get_project.return_value = project
        mock_get_name.return_value = "projectA"
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"
        mock_load_config.return_value = {"backend": "local"}

        mock_storage = MagicMock()
        mock_storage.upload.return_value = True
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(target=None, force=True)
        result = push_artifacts(args)

        assert result == 0
        # should_skip_upload should not be called when force=True
        mock_should_skip.assert_not_called()

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.get_project_name")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.should_skip_upload")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_respects_target_override(
        self,
        mock_get_storage,
        mock_should_skip,
        mock_load_config,
        mock_extract_target,
        mock_resolve_profiles,
        mock_get_name,
        mock_get_project,
        tmp_path,
    ):
        project = tmp_path / "project"
        project.mkdir()
        target_dir = project / "target"
        target_dir.mkdir()
        (target_dir / "manifest.json").touch()
        (target_dir / "run_results.json").touch()

        mock_get_project.return_value = project
        mock_get_name.return_value = "projectA"
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_load_config.return_value = {"backend": "local"}
        mock_should_skip.return_value = False

        mock_storage = MagicMock()
        mock_storage.upload.return_value = True
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(target="custom_target", force=False)
        result = push_artifacts(args)

        assert result == 0
        # extract_dbt_target should NOT be called when target is provided
        mock_extract_target.assert_not_called()
        mock_get_storage.assert_called_once()
        # Verify target was used
        call_args = mock_get_storage.call_args
        assert call_args[0][1] == "custom_target"


class TestPullArtifacts:
    """Tests for pull_artifacts() command."""

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_downloads_successfully(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
        capsys,
    ):
        project = tmp_path / "project"
        project.mkdir()

        mock_get_project.return_value = project
        mock_load_config.return_value = {"backend": "local"}
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"

        mock_storage = MagicMock()
        mock_storage.download.return_value = {
            "manifest_path": "/tmp/manifest.json",
            "run_results_path": "/tmp/run_results.json",
        }
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(project="upstreamProject", target=None, version=None)
        result = pull_artifacts(args)

        assert result == 0
        mock_storage.download.assert_called_once_with(version=None)

        captured = capsys.readouterr()
        assert "Successfully downloaded" in captured.out
        assert "upstreamProject" in captured.out

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_returns_error_when_download_fails(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
    ):
        project = tmp_path / "project"
        project.mkdir()

        mock_get_project.return_value = project
        mock_load_config.return_value = {"backend": "local"}
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"

        mock_storage = MagicMock()
        mock_storage.download.return_value = None
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(project="upstreamProject", target=None, version=None)
        result = pull_artifacts(args)

        assert result == 1

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_uses_cwd_when_no_project_dir_found(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
    ):
        mock_get_project.return_value = None

        mock_load_config.return_value = {"backend": "local"}
        mock_resolve_profiles.return_value = Path.cwd() / "profiles.yml"
        mock_extract_target.return_value = "dev"

        mock_storage = MagicMock()
        mock_storage.download.return_value = {
            "manifest_path": "/tmp/manifest.json",
            "run_results_path": "/tmp/run_results.json",
        }
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(project="upstreamProject", target=None, version=None)
        result = pull_artifacts(args)

        assert result == 0
        # Should still call load_artifact_config with Path.cwd()
        mock_load_config.assert_called_once()

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_downloads_specific_version(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
    ):
        project = tmp_path / "project"
        project.mkdir()

        mock_get_project.return_value = project
        mock_load_config.return_value = {"backend": "local"}
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"

        mock_storage = MagicMock()
        mock_storage.download.return_value = {
            "manifest_path": "/tmp/manifest.json",
            "run_results_path": "/tmp/run_results.json",
        }
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(
            project="upstreamProject", target=None, version="20240101_120000"
        )
        result = pull_artifacts(args)

        assert result == 0
        mock_storage.download.assert_called_once_with(version="20240101_120000")


class TestListArtifacts:
    """Tests for list_artifacts() command."""

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_lists_versions_successfully(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
        capsys,
    ):
        project = tmp_path / "project"
        project.mkdir()

        mock_get_project.return_value = project
        mock_load_config.return_value = {"backend": "local"}
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"

        mock_storage = MagicMock()
        mock_storage.list_versions.return_value = ["20240101_120000", "20240102_140000"]
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(project="upstreamProject", target=None)
        result = list_artifacts(args)

        assert result == 0

        captured = capsys.readouterr()
        assert "Available versions" in captured.out
        assert "20240101_120000" in captured.out
        assert "20240102_140000" in captured.out
        assert "latest" in captured.out

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_handles_no_versions(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
        capsys,
    ):
        project = tmp_path / "project"
        project.mkdir()

        mock_get_project.return_value = project
        mock_load_config.return_value = {"backend": "local"}
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"

        mock_storage = MagicMock()
        mock_storage.list_versions.return_value = []
        mock_get_storage.return_value = mock_storage

        args = argparse.Namespace(project="upstreamProject", target=None)
        result = list_artifacts(args)

        assert result == 0

        captured = capsys.readouterr()
        assert "No versions found" in captured.out

    @patch("xbt_loom_plugin.artifacts_cli._get_project_dir")
    @patch("xbt_loom_plugin.artifacts_cli.load_artifact_config")
    @patch("xbt_loom_plugin.artifacts_cli.resolve_profiles_path")
    @patch("xbt_loom_plugin.artifacts_cli.extract_dbt_target")
    @patch("xbt_loom_plugin.artifacts_cli.get_artifact_storage")
    def test_returns_error_when_storage_init_fails(
        self,
        mock_get_storage,
        mock_extract_target,
        mock_resolve_profiles,
        mock_load_config,
        mock_get_project,
        tmp_path,
    ):
        project = tmp_path / "project"
        project.mkdir()

        mock_get_project.return_value = project
        mock_load_config.return_value = {"backend": "invalid"}
        mock_resolve_profiles.return_value = project / "profiles.yml"
        mock_extract_target.return_value = "dev"
        mock_get_storage.return_value = None

        args = argparse.Namespace(project="upstreamProject", target=None)
        result = list_artifacts(args)

        assert result == 1


class TestMain:
    """Tests for main() CLI entry point."""

    def test_shows_help_when_no_command(self, capsys):
        with patch("sys.argv", ["xbt-artifacts"]):
            result = main()

        assert result == 0
        captured = capsys.readouterr()
        assert "Manage dbt artifact storage" in captured.out

    @patch("xbt_loom_plugin.artifacts_cli.push_artifacts")
    def test_calls_push_command(self, mock_push):
        mock_push.return_value = 0

        with patch("sys.argv", ["xbt-artifacts", "push"]):
            result = main()

        assert result == 0
        mock_push.assert_called_once()

    @patch("xbt_loom_plugin.artifacts_cli.pull_artifacts")
    def test_calls_pull_command(self, mock_pull):
        mock_pull.return_value = 0

        with patch("sys.argv", ["xbt-artifacts", "pull", "projectA"]):
            result = main()

        assert result == 0
        mock_pull.assert_called_once()

    @patch("xbt_loom_plugin.artifacts_cli.list_artifacts")
    def test_calls_list_command(self, mock_list):
        mock_list.return_value = 0

        with patch("sys.argv", ["xbt-artifacts", "list", "projectA"]):
            result = main()

        assert result == 0
        mock_list.assert_called_once()

    @patch("xbt_loom_plugin.artifacts_cli.push_artifacts")
    def test_parses_push_with_target(self, mock_push):
        mock_push.return_value = 0

        with patch("sys.argv", ["xbt-artifacts", "push", "--target", "prod"]):
            result = main()

        assert result == 0
        # Verify args were parsed correctly
        call_args = mock_push.call_args[0][0]
        assert call_args.target == "prod"

    @patch("xbt_loom_plugin.artifacts_cli.push_artifacts")
    def test_parses_push_with_force(self, mock_push):
        mock_push.return_value = 0

        with patch("sys.argv", ["xbt-artifacts", "push", "--force"]):
            result = main()

        assert result == 0
        call_args = mock_push.call_args[0][0]
        assert call_args.force is True

    @patch("xbt_loom_plugin.artifacts_cli.pull_artifacts")
    def test_parses_pull_with_version(self, mock_pull):
        mock_pull.return_value = 0

        with patch(
            "sys.argv",
            ["xbt-artifacts", "pull", "projectA", "--version", "20240101_120000"],
        ):
            result = main()

        assert result == 0
        call_args = mock_pull.call_args[0][0]
        assert call_args.project == "projectA"
        assert call_args.version == "20240101_120000"
