"""Tests for xbt_plugins.arg_parser module."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest

from xbt_loom_plugin.arg_parser import (
    find_profiles_dir,
    find_project_dir,
    parse_cli_args,
    resolve_profiles_dir,
    resolve_project_dir,
)


class TestParseCliArgs:
    """Test CLI argument parsing."""

    def test_parse_project_dir_with_value_format(self):
        """Test --project-dir value format."""
        args = ["dbt", "run", "--project-dir", "/path/to/project"]
        result = parse_cli_args(args)
        assert result["project_dir"] == "/path/to/project"
        assert result["profiles_dir"] is None

    def test_parse_project_dir_with_equals_format(self):
        """Test --project-dir=value format."""
        args = ["dbt", "run", "--project-dir=/path/to/project"]
        result = parse_cli_args(args)
        assert result["project_dir"] == "/path/to/project"

    def test_parse_profiles_dir_with_value_format(self):
        """Test --profiles-dir value format."""
        args = ["dbt", "run", "--profiles-dir", "/path/to/profiles"]
        result = parse_cli_args(args)
        assert result["profiles_dir"] == "/path/to/profiles"

    def test_parse_profiles_dir_with_equals_format(self):
        """Test --profiles-dir=value format."""
        args = ["dbt", "run", "--profiles-dir=/path/to/profiles"]
        result = parse_cli_args(args)
        assert result["profiles_dir"] == "/path/to/profiles"

    def test_parse_both_directories(self):
        """Test parsing both project and profiles directories."""
        args = [
            "dbt",
            "run",
            "--project-dir=/project",
            "--profiles-dir=/profiles",
        ]
        result = parse_cli_args(args)
        assert result["project_dir"] == "/project"
        assert result["profiles_dir"] == "/profiles"

    def test_parse_underscore_format(self):
        """Test underscore format: --project_dir."""
        args = ["dbt", "run", "--project_dir", "/path/to/project"]
        result = parse_cli_args(args)
        assert result["project_dir"] == "/path/to/project"

    def test_parse_empty_args(self):
        """Test parsing empty arguments."""
        args = []
        result = parse_cli_args(args)
        assert result["project_dir"] is None
        assert result["profiles_dir"] is None

    def test_parse_args_without_flags(self):
        """Test parsing args with other flags but not project/profiles."""
        args = ["dbt", "run", "--select", "model_name"]
        result = parse_cli_args(args)
        assert result["project_dir"] is None
        assert result["profiles_dir"] is None

    def test_parse_flag_at_end_without_value(self):
        """Test flag at end without value."""
        args = ["dbt", "run", "--profiles-dir"]
        result = parse_cli_args(args)
        assert result["profiles_dir"] is None


class TestFindProfilesDir:
    """Test profiles directory discovery."""

    def test_find_profiles_in_cwd(self, tmp_path, monkeypatch):
        """Test finding profiles.yml in current directory."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "profiles.yml").touch()

        result = find_profiles_dir()
        assert result == tmp_path

    def test_find_profiles_in_home_dbt(self, tmp_path, monkeypatch):
        """Test finding ~/.dbt/ directory."""
        monkeypatch.setenv("HOME", str(tmp_path))
        (tmp_path / ".dbt").mkdir()

        result = find_profiles_dir()
        assert result == tmp_path / ".dbt"

    def test_profiles_dir_not_found(self, tmp_path, monkeypatch):
        """Test when profiles directory not found."""
        monkeypatch.chdir(tmp_path)
        monkeypatch.setenv("HOME", str(tmp_path))

        result = find_profiles_dir()
        assert result is None


class TestFindProjectDir:
    """Test project directory discovery."""

    def test_find_project_in_cwd(self, tmp_path, monkeypatch):
        """Test finding dbt_project.yml in current directory."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "dbt_project.yml").touch()

        result = find_project_dir()
        assert result == tmp_path

    def test_project_dir_not_found(self, tmp_path, monkeypatch):
        """Test when project directory not found."""
        monkeypatch.chdir(tmp_path)

        result = find_project_dir()
        assert result is None


class TestResolveProfilesDir:
    """Test full profiles directory resolution."""

    def test_cli_arg_takes_priority(self, tmp_path):
        """Test CLI argument has highest priority."""
        cli_dir = tmp_path / "cli"
        cli_dir.mkdir()
        (cli_dir / "profiles.yml").touch()

        args = ["--profiles-dir", str(cli_dir)]
        result = resolve_profiles_dir(args)
        assert result == cli_dir

    def test_env_var_takes_priority_over_cwd(self, tmp_path, monkeypatch):
        """Test environment variable has priority over cwd."""
        env_dir = tmp_path / "env"
        env_dir.mkdir()
        (env_dir / "profiles.yml").touch()

        monkeypatch.setenv("DBT_PROFILES_DIR", str(env_dir))
        monkeypatch.chdir(tmp_path)

        args = []
        result = resolve_profiles_dir(args)
        assert result == env_dir

    def test_cwd_takes_priority_over_home_dbt(self, tmp_path, monkeypatch):
        """Test cwd has priority over ~/.dbt/."""
        home = tmp_path / "home"
        home.mkdir()
        cwd = tmp_path / "cwd"
        cwd.mkdir()

        (cwd / "profiles.yml").touch()
        (home / ".dbt").mkdir()

        monkeypatch.setenv("HOME", str(home))
        monkeypatch.chdir(cwd)

        args = []
        result = resolve_profiles_dir(args)
        assert result == cwd


class TestResolveProjectDir:
    """Test full project directory resolution."""

    def test_cli_arg_takes_priority(self, tmp_path):
        """Test CLI argument has highest priority."""
        cli_dir = tmp_path / "cli_project"
        cli_dir.mkdir()
        (cli_dir / "dbt_project.yml").touch()

        args = ["--project-dir", str(cli_dir)]
        result = resolve_project_dir(args)
        assert result == cli_dir

    def test_env_var_takes_priority_over_cwd(self, tmp_path, monkeypatch):
        """Test environment variable has priority over cwd."""
        env_dir = tmp_path / "env_project"
        env_dir.mkdir()
        (env_dir / "dbt_project.yml").touch()

        monkeypatch.setenv("DBT_PROJECT_DIR", str(env_dir))
        monkeypatch.chdir(tmp_path)

        args = []
        result = resolve_project_dir(args)
        assert result == env_dir

    def test_cwd_as_fallback(self, tmp_path, monkeypatch):
        """Test cwd as fallback."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / "dbt_project.yml").touch()

        args = []
        result = resolve_project_dir(args)
        assert result == tmp_path

    def test_project_dir_not_found(self, tmp_path, monkeypatch):
        """Test when project directory not found."""
        monkeypatch.chdir(tmp_path)

        args = []
        result = resolve_project_dir(args)
        assert result is None
