"""Tests for xbt_plugins.config_generator module."""

import pytest
import yaml

from xbt_loom_plugin.config_generator import (
    auto_configure_loom,
    extract_dependencies,
    extract_project_name,
    generate_config_for_project,
    read_dbt_project_yml,
    read_dependencies_yml,
    write_config_file,
)


class TestReadDbtProjectYml:
    """Test reading dbt_project.yml."""

    def test_read_valid_project_file(self, tmp_path):
        """Test reading valid dbt_project.yml."""
        project_file = tmp_path / "dbt_project.yml"
        project_file.write_text(yaml.dump({"name": "my_project", "version": "1.0.0"}))

        result = read_dbt_project_yml(tmp_path)
        assert result["name"] == "my_project"

    def test_read_missing_project_file(self, tmp_path):
        """Test error when dbt_project.yml not found."""
        with pytest.raises(FileNotFoundError):
            read_dbt_project_yml(tmp_path)


class TestExtractProjectName:
    """Test extracting project name."""

    def test_extract_name_from_project(self):
        """Test extracting name from project dict."""
        project = {"name": "analytics", "version": "1.0.0"}
        name = extract_project_name(project)
        assert name == "analytics"

    def test_extract_name_missing(self):
        """Test error when name field missing."""
        project = {"version": "1.0.0"}
        with pytest.raises(ValueError, match="'name'"):
            extract_project_name(project)


class TestReadDependenciesYml:
    """Test reading dependencies.yml."""

    def test_read_valid_dependencies_file(self, tmp_path):
        """Test reading valid dependencies.yml."""
        deps_file = tmp_path / "dependencies.yml"
        deps_file.write_text(yaml.dump({"projects": [{"name": "upstream_a"}]}))

        result = read_dependencies_yml(tmp_path)
        assert result is not None
        assert result["projects"][0]["name"] == "upstream_a"

    def test_read_missing_dependencies_file(self, tmp_path):
        """Test handling missing dependencies.yml."""
        result = read_dependencies_yml(tmp_path)
        assert result is None


class TestExtractDependencies:
    """Test extracting upstream projects."""

    def test_extract_dependencies_from_projects_list(self):
        """Test extracting valid dependencies."""
        deps = {"projects": [{"name": "projectA"}, {"name": "projectB"}]}
        entries = extract_dependencies(deps)
        names = [entry["name"] for entry in entries]
        assert names == ["projectA", "projectB"]

    def test_extract_no_dependencies(self):
        """Test when no dependencies exist."""
        deps = {"projects": []}
        entries = extract_dependencies(deps)
        assert entries == []

    def test_extract_from_none(self):
        """Test extracting from None."""
        entries = extract_dependencies(None)
        assert entries == []

    def test_extract_dependencies_invalid_project_format(self):
        """Test invalid project entries fail fast."""
        deps = {"projects": [{"name": "projectA"}, "invalid_entry"]}
        with pytest.raises(ValueError, match="Invalid project entry"):
            extract_dependencies(deps)

    def test_extract_dependencies_invalid_projects_shape(self):
        """Test invalid projects field shape fails."""
        deps = {"projects": {"name": "projectA"}}
        with pytest.raises(ValueError, match="must be a list"):
            extract_dependencies(deps)

    def test_extract_dependencies_invalid_config_type(self):
        """Test invalid config type fails."""
        deps = {"projects": [{"name": "projectA", "config": "bad"}]}
        with pytest.raises(ValueError, match="'config' must be a mapping"):
            extract_dependencies(deps)


class TestGenerateConfigForProject:
    """Test config generation for a project."""

    def test_generate_config_with_single_dependency(self, tmp_path):
        """Test generating config with one upstream project."""
        # Setup project
        project_dir = tmp_path / "projectB"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(
            yaml.dump({"name": "projectB", "version": "1.0.0"})
        )

        # Setup dependency
        upstream_dir = tmp_path / "projectA"
        upstream_dir.mkdir()
        (upstream_dir / "target").mkdir()
        (upstream_dir / "target" / "manifest.json").touch()

        # Setup dependencies.yml
        (project_dir / "dependencies.yml").write_text(
            yaml.dump({"projects": [{"name": "projectA"}]})
        )

        config_yaml = generate_config_for_project(
            project_dir, args=[], workspace_root=tmp_path
        )

        assert config_yaml is not None
        config = yaml.safe_load(config_yaml)

        assert "manifests" in config
        assert len(config["manifests"]) == 1
        assert config["manifests"][0]["name"] == "projectA"
        assert config["manifests"][0]["type"] == "file"

    def test_generate_config_no_dependencies(self, tmp_path):
        """Test generating config when no dependencies exist."""
        project_dir = tmp_path / "projectA"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectA"}))

        config_yaml = generate_config_for_project(project_dir)
        assert config_yaml is None

    def test_generate_config_multiple_dependencies(self, tmp_path):
        """Test generating config with multiple upstream projects."""
        project_dir = tmp_path / "projectC"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectC"}))

        (project_dir / "dependencies.yml").write_text(
            yaml.dump(
                {
                    "projects": [
                        {"name": "projectA"},
                        {"name": "projectB"},
                    ]
                }
            )
        )

        config_yaml = generate_config_for_project(project_dir, workspace_root=tmp_path)

        assert config_yaml is not None
        config = yaml.safe_load(config_yaml)

        assert len(config["manifests"]) == 2
        names = [m["name"] for m in config["manifests"]]
        assert "projectA" in names
        assert "projectB" in names

    def test_generate_config_non_file_without_config_fails(self, tmp_path):
        """Test non-file manifest type requires config."""
        project_dir = tmp_path / "projectB"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectB"}))
        (project_dir / "dependencies.yml").write_text(
            yaml.dump({"projects": [{"name": "projectA", "type": "s3"}]})
        )

        with pytest.raises(ValueError, match="Missing 'config'"):
            generate_config_for_project(project_dir, workspace_root=tmp_path)

    def test_generate_config_preserves_non_string_config_types(self, tmp_path):
        """Test nested non-string values remain native types in manifest config."""
        project_dir = tmp_path / "projectB"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectB"}))
        (project_dir / "dependencies.yml").write_text(
            yaml.dump(
                {
                    "projects": [
                        {
                            "name": "projectA",
                            "type": "s3",
                            "config": {
                                "bucket_name": "bucket",
                                "object_name": "prefix/{{ upstream_project }}/manifest.json",
                                "use_accelerate": True,
                                "retry_count": 3,
                                "regions": ["us-east-1", "${REGION_FALLBACK}"],
                                "metadata": {"owner": "{{ project_name }}"},
                            },
                        }
                    ]
                }
            )
        )

        config_yaml = generate_config_for_project(project_dir, workspace_root=tmp_path)
        assert config_yaml is not None
        config = yaml.safe_load(config_yaml)

        rendered = config["manifests"][0]["config"]
        assert rendered["use_accelerate"] is True
        assert rendered["retry_count"] == 3
        assert rendered["regions"][0] == "us-east-1"
        assert rendered["metadata"]["owner"] == "projectB"

    def test_generate_config_template_output_requires_manifests(self, tmp_path):
        """Test template output must include manifests."""
        project_dir = tmp_path / "projectB"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectB"}))
        (project_dir / "dependencies.yml").write_text(
            yaml.dump({"projects": [{"name": "projectA"}]})
        )
        (project_dir / "dbt_loom.config.template.yml").write_text("foo: bar\n")

        with pytest.raises(ValueError, match="must include top-level 'manifests'"):
            generate_config_for_project(project_dir, workspace_root=tmp_path)

    def test_generate_config_template_output_validates_manifest_config(self, tmp_path):
        """Test template-generated manifests are validated."""
        project_dir = tmp_path / "projectB"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "projectB"}))
        (project_dir / "dependencies.yml").write_text(
            yaml.dump({"projects": [{"name": "projectA"}]})
        )
        (project_dir / "dbt_loom.config.template.yml").write_text(
            """
manifests:
  - name: projectA
    type: file
    config: {}
""".strip()
            + "\n"
        )

        with pytest.raises(ValueError, match="requires 'path'"):
            generate_config_for_project(project_dir, workspace_root=tmp_path)


class TestWriteConfigFile:
    """Test writing config file."""

    def test_write_config_creates_file(self, tmp_path):
        """Test writing config file."""
        config_yaml = "manifests:\n  - name: test\n"
        result = write_config_file(tmp_path, config_yaml)

        config_file = tmp_path / "dbt_loom.config.yml"
        assert config_file.exists()
        assert result == config_file
        assert config_file.read_text() == config_yaml

    def test_write_config_overwrites_existing(self, tmp_path):
        """Test writing config overwrites existing file."""
        config_file = tmp_path / "dbt_loom.config.yml"
        config_file.write_text("old content")

        new_yaml = "new content"
        write_config_file(tmp_path, new_yaml)

        assert config_file.read_text() == new_yaml


class TestAutoConfigureLoom:
    """Test auto-configuration entry point."""

    def test_auto_configure_creates_config(self, tmp_path):
        """Test auto-configuration creates config file."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "project"}))
        (project_dir / "dependencies.yml").write_text(
            yaml.dump({"projects": [{"name": "upstream"}]})
        )

        result = auto_configure_loom(project_dir, workspace_root=tmp_path)

        assert result is not None
        assert result.name == "dbt_loom.config.yml"
        assert result.exists()

    def test_auto_configure_no_project_file(self, tmp_path):
        """Test auto-configure skips if no dbt_project.yml."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        result = auto_configure_loom(project_dir, workspace_root=tmp_path)
        assert result is None

    def test_auto_configure_no_dependencies(self, tmp_path):
        """Test auto-configure skips if no dependencies."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "project"}))

        result = auto_configure_loom(project_dir, workspace_root=tmp_path)
        assert result is None

    def test_auto_configure_with_args(self, tmp_path):
        """Test auto-configure with CLI args."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()
        (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": "project"}))
        (project_dir / "dependencies.yml").write_text(
            yaml.dump({"projects": [{"name": "upstream"}]})
        )

        args = ["--project-dir", str(project_dir)]
        result = auto_configure_loom(project_dir, args=args, workspace_root=tmp_path)

        assert result is not None
        assert result.exists()
