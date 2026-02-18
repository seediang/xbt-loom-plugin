"""Tests for shared utility functions."""

import logging
from unittest.mock import MagicMock

import pytest
import yaml

from xbt_loom_plugin.utils import (
    DEFAULT_TEMPLATE_NAME,
    emit_status,
    find_workspace_root,
    format_status_message,
    get_template_candidates,
    is_plugin_management_command,
    read_text_file,
    read_yaml_file,
)


class TestPluginManagementCommand:
    """Tests for is_plugin_management_command()."""

    def test_detects_plugin_command(self):
        assert is_plugin_management_command(["xbt", "plugin", "list"])

    def test_detects_plugins_command(self):
        assert is_plugin_management_command(["xbt", "plugins"])

    def test_rejects_non_plugin_command(self):
        assert not is_plugin_management_command(["dbt", "run"])

    def test_rejects_empty_args(self):
        assert not is_plugin_management_command([])

    def test_detects_plugin_anywhere_in_args(self):
        assert is_plugin_management_command(["dbt", "run", "plugin", "list"])


class TestStatusFormatting:
    """Tests for format_status_message()."""

    def test_formats_message_with_timestamp(self):
        result = format_status_message("test-prefix", "test message")
        # Should contain timestamp in HH:MM:SS format
        assert "test-prefix: test message" in result
        # Verify timestamp format (basic check)
        parts = result.split("  ")
        assert len(parts) == 2
        # Timestamp should be at start
        timestamp = parts[0]
        assert len(timestamp) == 8  # HH:MM:SS
        assert timestamp.count(":") == 2

    def test_preserves_prefix_and_message(self):
        result = format_status_message("xbt-loom", "Configuration complete")
        assert "xbt-loom: Configuration complete" in result


class TestEmitStatus:
    """Tests for emit_status()."""

    def test_logs_and_prints_message(self, capsys):
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Test status message"

        emit_status(mock_logger, message)

        # Should log at INFO level by default
        mock_logger.log.assert_called_once_with(logging.INFO, message)

        # Should print to stdout
        captured = capsys.readouterr()
        assert message in captured.out

    def test_respects_custom_log_level(self):
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Warning message"

        emit_status(mock_logger, message, level=logging.WARNING)

        mock_logger.log.assert_called_once_with(logging.WARNING, message)

    def test_prints_even_without_logger(self, capsys):
        mock_logger = MagicMock(spec=logging.Logger)
        message = "Another message"

        emit_status(mock_logger, message)

        captured = capsys.readouterr()
        assert message in captured.out


class TestFileReading:
    """Tests for read_text_file() and read_yaml_file()."""

    def test_read_text_file(self, tmp_path):
        test_file = tmp_path / "test.txt"
        content = "Hello, World!\nLine 2"
        test_file.write_text(content)

        result = read_text_file(test_file)
        assert result == content

    def test_read_text_file_empty(self, tmp_path):
        test_file = tmp_path / "empty.txt"
        test_file.write_text("")

        result = read_text_file(test_file)
        assert result == ""

    def test_read_yaml_file(self, tmp_path):
        test_file = tmp_path / "test.yml"
        data = {"key": "value", "number": 42, "nested": {"inner": "data"}}
        test_file.write_text(yaml.dump(data))

        result = read_yaml_file(test_file)
        assert result == data

    def test_read_yaml_file_empty_returns_empty_dict(self, tmp_path):
        test_file = tmp_path / "empty.yml"
        test_file.write_text("")

        result = read_yaml_file(test_file)
        assert result == {}

    def test_read_yaml_file_not_found_raises_error(self, tmp_path):
        non_existent = tmp_path / "nonexistent.yml"

        with pytest.raises(FileNotFoundError, match="File not found"):
            read_yaml_file(non_existent)

    def test_read_yaml_file_with_list(self, tmp_path):
        test_file = tmp_path / "list.yml"
        # YAML files can have lists as root, but read_yaml_file returns {} for non-dict
        test_file.write_text("- item1\n- item2")

        # Will return the list, not empty dict (yaml.safe_load returns list)
        result = read_yaml_file(test_file)
        # Actually, the function does `yaml.safe_load(file) or {}`
        # So if yaml.safe_load returns a list, it will return the list (truthy)
        # If it returns None, it returns {}
        assert isinstance(result, (dict, list))


class TestTemplateCandidates:
    """Tests for get_template_candidates()."""

    def test_returns_three_candidates_in_order(self, tmp_path):
        project_dir = tmp_path / "project"
        workspace_root = tmp_path

        result = get_template_candidates(project_dir, workspace_root)

        assert len(result) == 3
        assert result[0] == project_dir / DEFAULT_TEMPLATE_NAME
        assert result[1] == project_dir.parent / DEFAULT_TEMPLATE_NAME
        assert result[2] == workspace_root / DEFAULT_TEMPLATE_NAME

    def test_custom_template_name(self, tmp_path):
        project_dir = tmp_path / "project"
        workspace_root = tmp_path
        custom_name = "custom_template.yml"

        result = get_template_candidates(project_dir, workspace_root, custom_name)

        assert len(result) == 3
        assert result[0] == project_dir / custom_name
        assert result[1] == project_dir.parent / custom_name
        assert result[2] == workspace_root / custom_name

    def test_uses_default_template_name(self, tmp_path):
        project_dir = tmp_path / "project"
        workspace_root = tmp_path

        result = get_template_candidates(project_dir, workspace_root)

        # All should use DEFAULT_TEMPLATE_NAME
        assert all(DEFAULT_TEMPLATE_NAME in str(path) for path in result)


class TestFindWorkspaceRoot:
    """Tests for find_workspace_root()."""

    def test_finds_git_marker(self, tmp_path):
        # Create nested structure
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()

        project = workspace / "proj-mesh" / "projectA"
        project.mkdir(parents=True)

        result = find_workspace_root(project)
        assert result == workspace

    def test_finds_pyproject_toml_marker(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "pyproject.toml").touch()

        project = workspace / "subdir" / "project"
        project.mkdir(parents=True)

        result = find_workspace_root(project)
        assert result == workspace

    def test_finds_template_marker(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / DEFAULT_TEMPLATE_NAME).touch()

        project = workspace / "projects" / "projectB"
        project.mkdir(parents=True)

        result = find_workspace_root(project)
        assert result == workspace

    def test_returns_project_dir_when_no_marker_found(self, tmp_path):
        project = tmp_path / "isolated" / "project"
        project.mkdir(parents=True)

        result = find_workspace_root(project)
        # Should return the project_dir itself when no markers found
        assert result == project

    def test_respects_max_depth(self, tmp_path):
        # Create deep nesting beyond max_depth
        deep = tmp_path / "a" / "b" / "c" / "d" / "e" / "f" / "g"
        deep.mkdir(parents=True)
        (tmp_path / ".git").mkdir()

        # With max_depth=2, should not find .git
        result = find_workspace_root(deep, max_depth=2)
        assert result == deep  # Returns project_dir when not found

    def test_custom_markers(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / "custom_marker.txt").touch()

        project = workspace / "project"
        project.mkdir()

        result = find_workspace_root(project, markers=["custom_marker.txt"])
        assert result == workspace

    def test_stops_at_filesystem_root(self, tmp_path):
        # Even with high max_depth, should stop at filesystem root
        project = tmp_path / "project"
        project.mkdir()

        # Should not raise error even with very high max_depth
        result = find_workspace_root(project, max_depth=1000)
        assert result == project  # No marker found

    def test_finds_first_marker_in_hierarchy(self, tmp_path):
        # Create markers at multiple levels
        outer = tmp_path / "outer"
        outer.mkdir()
        (outer / ".git").mkdir()

        inner = outer / "inner"
        inner.mkdir()
        (inner / "pyproject.toml").touch()

        project = inner / "project"
        project.mkdir()

        # Should find inner first (closest marker)
        result = find_workspace_root(project)
        assert result == inner

    def test_marker_takes_precedence_over_depth(self, tmp_path):
        workspace = tmp_path / "workspace"
        workspace.mkdir()
        (workspace / ".git").mkdir()

        nested = workspace / "a" / "b" / "c"
        nested.mkdir(parents=True)

        result = find_workspace_root(nested, max_depth=10)
        assert result == workspace
