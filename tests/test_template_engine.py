"""Tests for xbt_plugins.template_engine module."""

import os
from pathlib import Path

import pytest

from xbt_loom_plugin.template_engine import (
    build_template_context,
    render_jinja2,
    render_value,
    substitute_env_vars,
)


class TestSubstituteEnvVars:
    """Test environment variable substitution."""

    def test_substitute_braced_env_var(self, monkeypatch):
        """Test ${VAR_NAME} format."""
        monkeypatch.setenv("MY_VAR", "value123")
        result = substitute_env_vars("Path: ${MY_VAR}/file")
        assert result == "Path: value123/file"

    def test_substitute_unbraced_env_var(self, monkeypatch):
        """Test $VAR_NAME format."""
        monkeypatch.setenv("MY_VAR", "value123")
        result = substitute_env_vars("Path: $MY_VAR/file")
        assert result == "Path: value123/file"

    def test_substitute_multiple_vars(self, monkeypatch):
        """Test multiple variable substitutions."""
        monkeypatch.setenv("VAR1", "hello")
        monkeypatch.setenv("VAR2", "world")
        result = substitute_env_vars("${VAR1} $VAR2")
        assert result == "hello world"

    def test_unknown_var_left_unchanged(self):
        """Test unknown variables left unchanged."""
        result = substitute_env_vars("${UNKNOWN_VAR}")
        assert result == "${UNKNOWN_VAR}"

    def test_no_vars(self):
        """Test string with no variables."""
        result = substitute_env_vars("Just plain text")
        assert result == "Just plain text"

    def test_mixed_formats(self, monkeypatch):
        """Test mixed ${} and $ formats."""
        monkeypatch.setenv("HOME", "/home/user")
        monkeypatch.setenv("USER", "testuser")
        result = substitute_env_vars("${HOME}/$USER/.config")
        assert result == "/home/user/testuser/.config"


class TestRenderJinja2:
    """Test Jinja2 template rendering."""

    def test_render_simple_variable(self):
        """Test rendering simple variable."""
        context = {"name": "Alice"}
        result = render_jinja2("Hello {{ name }}", context)
        assert result == "Hello Alice"

    def test_render_with_default_filter(self):
        """Test Jinja2 default filter."""
        context = {"optional_var": None}
        result = render_jinja2(
            "Value: {{ optional_var | default('fallback', true) }}", context
        )
        assert result == "Value: fallback"

    def test_render_expression(self):
        """Test rendering Jinja2 expression."""
        context = {"x": 5, "y": 3}
        result = render_jinja2("Sum: {{ x + y }}", context)
        assert result == "Sum: 8"

    def test_render_with_missing_variable(self):
        """Test rendering with missing variable in StrictUndefined mode."""
        context = {"name": "Alice"}
        with pytest.raises(Exception):
            render_jinja2("Hello {{ undefined_var }}", context)

    def test_render_no_template(self):
        """Test rendering plain text."""
        result = render_jinja2("Plain text", {})
        assert result == "Plain text"


class TestRenderValue:
    """Test combined Jinja2 and env var rendering."""

    def test_render_jinja2_then_env_vars(self, monkeypatch):
        """Test Jinja2 rendered first, then env vars."""
        monkeypatch.setenv("PROJECT", "myproject")
        context = {"name": "${PROJECT}"}
        result = render_value("Hello {{ name }}", context)
        assert result == "Hello myproject"

    def test_render_only_env_vars(self, monkeypatch):
        """Test rendering with only env vars."""
        monkeypatch.setenv("HOME", "/home/user")
        result = render_value("${HOME}/.config", {})
        assert result == "/home/user/.config"

    def test_render_only_jinja2(self):
        """Test rendering with only Jinja2."""
        context = {"upstream": "other_project"}
        result = render_value("../{{ upstream }}/target", context)
        assert result == "../other_project/target"

    def test_render_both_jinja2_and_env_vars(self, monkeypatch):
        """Test rendering with both Jinja2 and env vars."""
        monkeypatch.setenv("BASE_PATH", "/data")
        context = {"project": "analytics"}
        result = render_value("${BASE_PATH}/{{ project }}/manifest.json", context)
        assert result == "/data/analytics/manifest.json"

    def test_render_non_string(self):
        """Test rendering non-string value."""
        result = render_value(123, {})
        assert result == "123"


class TestBuildTemplateContext:
    """Test template context building."""

    def test_build_basic_context(self, tmp_path):
        """Test building basic context."""
        project_root = tmp_path / "myproject"
        context = build_template_context(
            upstream_project="upstream",
            project_root=project_root,
            project_name="myproject",
        )

        assert context["upstream_project"] == "upstream"
        assert context["project_root"] == str(project_root)
        assert context["project_name"] == "myproject"
        assert "manifest_path" in context

    def test_build_context_with_profiles_dir(self, tmp_path):
        """Test building context with profiles directory."""
        project_root = tmp_path / "myproject"
        profiles_dir = tmp_path / "profiles"

        context = build_template_context(
            upstream_project="upstream",
            project_root=project_root,
            profiles_dir=profiles_dir,
        )

        assert context["profiles_dir"] == str(profiles_dir)

    def test_context_manifest_path_default(self, tmp_path):
        """Test manifest path computed correctly."""
        project_root = tmp_path / "myproject"

        # Create upstream directory
        upstream_dir = tmp_path / "upstream" / "target"
        upstream_dir.mkdir(parents=True)

        context = build_template_context(
            upstream_project="upstream",
            project_root=project_root,
        )

        assert context["manifest_path"] == "../upstream/target/manifest.json"
        assert "manifest_path_abs" in context

    def test_context_with_custom_manifest_path(self, tmp_path):
        """Test context with pre-computed manifest path."""
        project_root = tmp_path / "myproject"
        custom_path = "/s3/bucket/manifest.json"

        context = build_template_context(
            upstream_project="upstream",
            project_root=project_root,
            manifest_path=custom_path,
        )

        assert context["manifest_path"] == custom_path
