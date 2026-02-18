"""Integration tests for the dbt-loom auto-configuration plugin."""

import pytest
import yaml

from xbt_loom_plugin.auto_configuration import xbt_pre_invoke


@pytest.fixture
def multi_project_setup(tmp_path):
    """Set up a multi-project dbt workspace."""
    # Create projectA (no dependencies)
    projectA = tmp_path / "projectA"
    projectA.mkdir()
    (projectA / "dbt_project.yml").write_text(
        yaml.dump({"name": "projectA", "version": "1.0.0"})
    )
    (projectA / "profiles.yml").write_text(
        yaml.dump({"projectA": {"outputs": {"dev": {}}, "target": "dev"}})
    )
    (projectA / "target").mkdir()
    (projectA / "target" / "manifest.json").write_text("{}")

    # Create projectB (depends on projectA)
    projectB = tmp_path / "projectB"
    projectB.mkdir()
    (projectB / "dbt_project.yml").write_text(
        yaml.dump({"name": "projectB", "version": "1.0.0"})
    )
    (projectB / "profiles.yml").write_text(
        yaml.dump({"projectB": {"outputs": {"dev": {}}, "target": "dev"}})
    )
    (projectB / "dependencies.yml").write_text(
        yaml.dump({"projects": [{"name": "projectA"}]})
    )

    return {"root": tmp_path, "projectA": projectA, "projectB": projectB}


class TestPluginHookIntegration:
    """Integration tests for xbt_pre_invoke hook."""

    def test_hook_generates_config_for_project(self, multi_project_setup):
        """Test hook generates config when invoked with project."""
        setup = multi_project_setup
        projectB = setup["projectB"]

        # Simulate being in projectB
        args = ["dbt", "run", "--project-dir", str(projectB)]

        result = xbt_pre_invoke(args)

        # Hook should return None (no modification to args)
        assert result is None

        # Config file should be generated
        config_file = projectB / "dbt_loom.config.yml"
        assert config_file.exists()

        # Verify content
        config = yaml.safe_load(config_file.read_text())
        assert "manifests" in config
        assert len(config["manifests"]) == 1
        assert config["manifests"][0]["name"] == "projectA"

    def test_hook_skips_project_without_dependencies(self, multi_project_setup):
        """Test hook skips project with no dependencies."""
        setup = multi_project_setup
        projectA = setup["projectA"]

        args = ["dbt", "run", "--project-dir", str(projectA)]

        result = xbt_pre_invoke(args)

        assert result is None

        # Config file should NOT be generated
        config_file = projectA / "dbt_loom.config.yml"
        assert not config_file.exists()

    def test_hook_with_env_var(self, multi_project_setup, monkeypatch):
        """Test hook respects DBT_PROJECT_DIR environment variable."""
        setup = multi_project_setup
        projectB = setup["projectB"]

        monkeypatch.setenv("DBT_PROJECT_DIR", str(projectB))

        # Args without explicit project-dir
        args = ["dbt", "run"]

        result = xbt_pre_invoke(args)

        assert result is None

        config_file = projectB / "dbt_loom.config.yml"
        assert config_file.exists()

    def test_hook_handles_errors_gracefully(self, tmp_path):
        """Test hook handles errors gracefully without crashing."""
        # Invalid project directory
        args = ["dbt", "run", "--project-dir", str(tmp_path / "nonexistent")]

        # Should not raise exception
        result = xbt_pre_invoke(args)
        assert result is None

    def test_hook_preserves_args(self, multi_project_setup):
        """Test hook doesn't modify arguments."""
        setup = multi_project_setup
        projectB = setup["projectB"]

        original_args = [
            "dbt",
            "run",
            "--select",
            "model1",
            "--project-dir",
            str(projectB),
        ]

        result = xbt_pre_invoke(original_args)

        # Args should be unchanged
        assert result is None


class TestConfigGeneration:
    """Test complete config generation workflow."""

    def test_config_generated_with_correct_manifest_path(self, multi_project_setup):
        """Test generated config has correct manifest path."""
        setup = multi_project_setup
        projectB = setup["projectB"]

        args = ["dbt", "run", "--project-dir", str(projectB)]
        xbt_pre_invoke(args)

        config_file = projectB / "dbt_loom.config.yml"
        config = yaml.safe_load(config_file.read_text())

        manifest_entry = config["manifests"][0]
        # Path should reference projectA
        assert "projectA" in manifest_entry["config"]["path"]
        assert "manifest.json" in manifest_entry["config"]["path"]

    def test_multiple_dependencies_generates_multiple_manifests(self, tmp_path):
        """Test project with multiple dependencies generates all manifests."""
        # Create three projects
        for proj_name in ["projectA", "projectB", "projectC"]:
            project_dir = tmp_path / proj_name
            project_dir.mkdir()
            (project_dir / "dbt_project.yml").write_text(yaml.dump({"name": proj_name}))
            (project_dir / "target").mkdir()
            (project_dir / "target" / "manifest.json").write_text("{}")

        # ProjectD depends on A, B, C
        projectD = tmp_path / "projectD"
        projectD.mkdir()
        (projectD / "dbt_project.yml").write_text(yaml.dump({"name": "projectD"}))
        (projectD / "dependencies.yml").write_text(
            yaml.dump(
                {
                    "projects": [
                        {"name": "projectA"},
                        {"name": "projectB"},
                        {"name": "projectC"},
                    ]
                }
            )
        )

        args = ["--project-dir", str(projectD)]
        xbt_pre_invoke(args)

        config_file = projectD / "dbt_loom.config.yml"
        config = yaml.safe_load(config_file.read_text())

        assert len(config["manifests"]) == 3
        names = {m["name"] for m in config["manifests"]}
        assert names == {"projectA", "projectB", "projectC"}

    def test_config_idempotency(self, multi_project_setup):
        """Test running hook multiple times produces identical output."""
        setup = multi_project_setup
        projectB = setup["projectB"]
        args = ["--project-dir", str(projectB)]

        # First run
        xbt_pre_invoke(args)
        config_file = projectB / "dbt_loom.config.yml"
        first_content = config_file.read_text()

        # Second run
        xbt_pre_invoke(args)
        second_content = config_file.read_text()

        assert first_content == second_content
