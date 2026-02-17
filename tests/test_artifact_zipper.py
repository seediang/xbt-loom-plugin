"""Tests for xbt_loom_plugin.artifact_zipper module."""

from pathlib import Path
import zipfile

from xbt_loom_plugin.artifact_zipper import xbt_post_invoke


class TestArtifactZipper:
    """Test artifact zip hook behavior."""

    def test_zip_artifacts_created(self, tmp_path):
        """Zip file is created with manifest and run_results."""
        project_dir = tmp_path / "project"
        target_dir = project_dir / "target"
        target_dir.mkdir(parents=True)

        (target_dir / "manifest.json").write_text("{}")
        (target_dir / "run_results.json").write_text("{}")

        args = ["dbt", "run", "--project-dir", str(project_dir)]
        xbt_post_invoke(args, result=None)

        zip_path = project_dir / "dbt_artifacts.zip"
        assert zip_path.exists()

        with zipfile.ZipFile(zip_path, "r") as zipf:
            names = sorted(zipf.namelist())

        assert names == ["manifest.json", "run_results.json"]

    def test_zip_skipped_when_no_artifacts(self, tmp_path):
        """Zip file is not created when target artifacts are missing."""
        project_dir = tmp_path / "project"
        project_dir.mkdir()

        args = ["dbt", "run", "--project-dir", str(project_dir)]
        xbt_post_invoke(args, result=None)

        zip_path = project_dir / "dbt_artifacts.zip"
        assert not zip_path.exists()
