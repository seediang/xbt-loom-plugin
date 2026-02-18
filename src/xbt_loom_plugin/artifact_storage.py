"""Artifact storage abstraction layer for multi-backend support."""

import gzip
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Optional, Union

import boto3
from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)


class ArtifactStorage(ABC):
    """Abstract base class for artifact storage backends."""

    def __init__(self, target_name: str, project_name: str):
        """Initialize storage backend.

        Args:
            target_name: dbt target name (e.g., 'dev', 'prod', 'staging')
            project_name: dbt project name
        """
        self.target_name = target_name
        self.project_name = project_name
        self.timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")

    @abstractmethod
    def upload(self, manifest_path: str, run_results_path: str) -> bool:
        """Upload artifacts to storage backend.

        Args:
            manifest_path: Path to manifest.json file
            run_results_path: Path to run_results.json file

        Returns:
            True if successful, False otherwise
        """
        pass

    @abstractmethod
    def download(
        self,
        version: Optional[str] = None,
        temp_dir: Optional[Union[str, Path]] = None,
    ) -> dict[str, str]:
        """Download artifacts from storage backend.

        Args:
            version: Specific version timestamp to download. If None, downloads 'latest'
            temp_dir: Temporary directory to extract artifacts. If None, creates one.

        Returns:
            Dictionary with 'manifest_path' and 'run_results_path' keys
        """
        pass

    @abstractmethod
    def list_versions(self) -> list:
        """List available artifact versions for this project/target.

        Returns:
            List of version timestamps (excluding 'latest')
        """
        pass

    def _build_path(self, *parts: str) -> str:
        """Build storage path from components."""
        return f"{self.target_name}/{self.project_name}/" + "/".join(parts)


class LocalArtifactStorage(ArtifactStorage):
    """Local filesystem artifact storage backend."""

    def __init__(self, target_name: str, project_name: str, base_path: str):
        """Initialize local storage.

        Args:
            target_name: dbt target name
            project_name: dbt project name
            base_path: Base directory for artifacts
        """
        super().__init__(target_name, project_name)
        self.base_path = Path(base_path)
        self.base_path.mkdir(parents=True, exist_ok=True)

    def upload(self, manifest_path: str, run_results_path: str) -> bool:
        """Upload artifacts to local filesystem."""
        try:
            project_dir = self.base_path / self.target_name / self.project_name
            project_dir.mkdir(parents=True, exist_ok=True)

            # Create timestamped version folder
            version_dir = project_dir / self.timestamp
            version_dir.mkdir(parents=True, exist_ok=True)

            # Gzip and upload manifest
            with open(manifest_path, "rb") as f_in:
                manifest_data = f_in.read()
            with gzip.open(version_dir / "manifest.json.gz", "wb") as f_out:
                f_out.write(manifest_data)

            # Gzip and upload run_results
            with open(run_results_path, "rb") as f_in:
                run_results_data = f_in.read()
            with gzip.open(version_dir / "run_results.json.gz", "wb") as f_out:
                f_out.write(run_results_data)

            # Update latest pointer
            latest_dir = project_dir / "latest"
            latest_dir.mkdir(parents=True, exist_ok=True)

            with gzip.open(latest_dir / "manifest.json.gz", "wb") as f_out:
                f_out.write(manifest_data)
            with gzip.open(latest_dir / "run_results.json.gz", "wb") as f_out:
                f_out.write(run_results_data)

            logger.info(
                f"Uploaded artifacts to local storage: {project_dir}/{self.timestamp}/"
            )
            return True
        except Exception as e:
            logger.error(f"Failed to upload artifacts to local storage: {e}")
            return False

    def download(
        self,
        version: Optional[str] = None,
        temp_dir: Optional[Union[str, Path]] = None,
    ) -> dict[str, str]:
        """Download artifacts from local filesystem."""
        try:
            version_folder = "latest" if version is None else version
            source_dir = (
                self.base_path / self.target_name / self.project_name / version_folder
            )

            if not source_dir.exists():
                logger.error(f"Artifact folder not found: {source_dir}")
                return {}

            # Create temp directory if not provided
            if temp_dir is None:
                temp_dir = Path("/tmp") / f"xbt_artifacts_{self.timestamp}"
            else:
                temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Extract gzipped files
            manifest_gz = source_dir / "manifest.json.gz"
            run_results_gz = source_dir / "run_results.json.gz"

            if not manifest_gz.exists() or not run_results_gz.exists():
                logger.error(f"Required artifact files not found in {source_dir}")
                return {}

            manifest_path = temp_dir / "manifest.json"
            run_results_path = temp_dir / "run_results.json"

            with gzip.open(manifest_gz, "rb") as f_in:
                manifest_path.write_bytes(f_in.read())

            with gzip.open(run_results_gz, "rb") as f_in:
                run_results_path.write_bytes(f_in.read())

            logger.info(
                f"Downloaded artifacts from local storage: {source_dir} to {temp_dir}"
            )
            return {
                "manifest_path": str(manifest_path),
                "run_results_path": str(run_results_path),
            }
        except Exception as e:
            logger.error(f"Failed to download artifacts from local storage: {e}")
            return {}

    def list_versions(self) -> list:
        """List available artifact versions."""
        try:
            project_dir = self.base_path / self.target_name / self.project_name
            if not project_dir.exists():
                return []

            versions = [
                d.name
                for d in project_dir.iterdir()
                if d.is_dir() and d.name != "latest"
            ]
            return sorted(versions, reverse=True)
        except Exception as e:
            logger.error(f"Failed to list versions: {e}")
            return []


class S3ArtifactStorage(ArtifactStorage):
    """AWS S3 artifact storage backend."""

    def __init__(
        self,
        target_name: str,
        project_name: str,
        bucket_name: str,
        aws_region: str = "us-east-1",
    ):
        """Initialize S3 storage.

        Args:
            target_name: dbt target name
            project_name: dbt project name
            bucket_name: S3 bucket name
            aws_region: AWS region
        """
        super().__init__(target_name, project_name)
        self.bucket_name = bucket_name
        self.s3_client = boto3.client("s3", region_name=aws_region)
        self.s3_prefix = f"xbt-loom-artifacts/{self.target_name}/{self.project_name}"

    def upload(self, manifest_path: str, run_results_path: str) -> bool:
        """Upload artifacts to S3."""
        try:
            # Read and gzip manifest
            with open(manifest_path, "rb") as f:
                manifest_data = f.read()
            manifest_gz = gzip.compress(manifest_data)

            # Read and gzip run_results
            with open(run_results_path, "rb") as f:
                run_results_data = f.read()
            run_results_gz = gzip.compress(run_results_data)

            # Upload to versioned folder
            version_prefix = f"{self.s3_prefix}/{self.timestamp}"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{version_prefix}/manifest.json.gz",
                Body=manifest_gz,
            )
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{version_prefix}/run_results.json.gz",
                Body=run_results_gz,
            )

            # Upload to latest folder
            latest_prefix = f"{self.s3_prefix}/latest"
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{latest_prefix}/manifest.json.gz",
                Body=manifest_gz,
            )
            self.s3_client.put_object(
                Bucket=self.bucket_name,
                Key=f"{latest_prefix}/run_results.json.gz",
                Body=run_results_gz,
            )

            logger.info(
                f"Uploaded artifacts to S3: s3://{self.bucket_name}/{version_prefix}/"
            )
            return True
        except ClientError as e:
            logger.error(f"Failed to upload artifacts to S3: {e}")
            return False

    def download(
        self,
        version: Optional[str] = None,
        temp_dir: Optional[Union[str, Path]] = None,
    ) -> dict[str, str]:
        """Download artifacts from S3."""
        try:
            version_folder = "latest" if version is None else version
            source_prefix = f"{self.s3_prefix}/{version_folder}"

            # Create temp directory if not provided
            if temp_dir is None:
                temp_dir = Path("/tmp") / f"xbt_artifacts_{self.timestamp}"
            else:
                temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Download and decompress manifest
            manifest_key = f"{source_prefix}/manifest.json.gz"
            run_results_key = f"{source_prefix}/run_results.json.gz"

            try:
                manifest_gz = self.s3_client.get_object(
                    Bucket=self.bucket_name, Key=manifest_key
                )["Body"].read()
                manifest_data = gzip.decompress(manifest_gz)
            except Exception as e:
                logger.error(f"Failed to download manifest from S3: {e}")
                return {}

            try:
                run_results_gz = self.s3_client.get_object(
                    Bucket=self.bucket_name, Key=run_results_key
                )["Body"].read()
                run_results_data = gzip.decompress(run_results_gz)
            except Exception as e:
                logger.error(f"Failed to download run_results from S3: {e}")
                return {}

            # Write to temp directory
            manifest_path = temp_dir / "manifest.json"
            run_results_path = temp_dir / "run_results.json"

            manifest_path.write_bytes(manifest_data)
            run_results_path.write_bytes(run_results_data)

            logger.info(
                f"Downloaded artifacts from S3: s3://{self.bucket_name}/{source_prefix}/ "
                f"to {temp_dir}"
            )
            return {
                "manifest_path": str(manifest_path),
                "run_results_path": str(run_results_path),
            }
        except Exception as e:
            logger.error(f"Failed to download artifacts from S3: {e}")
            return {}

    def list_versions(self) -> list:
        """List available artifact versions in S3."""
        try:
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name, Prefix=f"{self.s3_prefix}/", Delimiter="/"
            )

            if "CommonPrefixes" not in response:
                return []

            versions = [
                prefix["Prefix"].split("/")[-2]
                for prefix in response["CommonPrefixes"]
                if prefix["Prefix"].split("/")[-2] != "latest"
            ]
            return sorted(versions, reverse=True)
        except ClientError as e:
            logger.error(f"Failed to list S3 versions: {e}")
            return []


class SnowflakeArtifactStorage(ArtifactStorage):
    """Snowflake stage artifact storage backend."""

    def __init__(
        self,
        target_name: str,
        project_name: str,
        stage_path: str,
        snowflake_connection=None,
    ):
        """Initialize Snowflake storage.

        Args:
            target_name: dbt target name
            project_name: dbt project name
            stage_path: Snowflake stage path (e.g., '@my_stage')
            snowflake_connection: Optional Snowflake connection object
        """
        super().__init__(target_name, project_name)
        self.stage_path = stage_path
        self.snowflake_connection = snowflake_connection
        self.prefix = f"xbt-loom-artifacts/{self.target_name}/{self.project_name}"

    def upload(self, manifest_path: str, run_results_path: str) -> bool:
        """Upload artifacts to Snowflake stage."""
        try:
            if self.snowflake_connection is None:
                logger.error("Snowflake connection not available for upload")
                return False

            # Read and gzip files
            with open(manifest_path, "rb") as f:
                manifest_data = f.read()
            manifest_gz = gzip.compress(manifest_data)

            with open(run_results_path, "rb") as f:
                run_results_data = f.read()
            run_results_gz = gzip.compress(run_results_data)

            # Create temporary local files for upload
            temp_dir = Path("/tmp") / f"snowflake_upload_{self.timestamp}"
            temp_dir.mkdir(parents=True, exist_ok=True)

            manifest_gz_path = temp_dir / "manifest.json.gz"
            run_results_gz_path = temp_dir / "run_results.json.gz"

            manifest_gz_path.write_bytes(manifest_gz)
            run_results_gz_path.write_bytes(run_results_gz)

            # Upload using Snowflake PUT command
            version_stage_path = f"{self.stage_path}/{self.prefix}/{self.timestamp}"

            cursor = self.snowflake_connection.cursor()
            cursor.execute(f"PUT file://{manifest_gz_path} {version_stage_path}/")
            cursor.execute(f"PUT file://{run_results_gz_path} {version_stage_path}/")

            # Update latest
            latest_stage_path = f"{self.stage_path}/{self.prefix}/latest"
            cursor.execute(f"PUT file://{manifest_gz_path} {latest_stage_path}/")
            cursor.execute(f"PUT file://{run_results_gz_path} {latest_stage_path}/")

            cursor.close()
            logger.info(f"Uploaded artifacts to Snowflake: {version_stage_path}/")
            return True
        except Exception as e:
            logger.error(f"Failed to upload artifacts to Snowflake: {e}")
            return False

    def download(
        self,
        version: Optional[str] = None,
        temp_dir: Optional[Union[str, Path]] = None,
    ) -> dict[str, str]:
        """Download artifacts from Snowflake stage."""
        try:
            if self.snowflake_connection is None:
                logger.error("Snowflake connection not available for download")
                return {}

            version_folder = "latest" if version is None else version

            # Create temp directory if not provided
            if temp_dir is None:
                temp_dir = Path("/tmp") / f"xbt_artifacts_{self.timestamp}"
            else:
                temp_dir = Path(temp_dir)
            temp_dir.mkdir(parents=True, exist_ok=True)

            # Download using Snowflake GET command
            source_stage_path = f"{self.stage_path}/{self.prefix}/{version_folder}"

            cursor = self.snowflake_connection.cursor()
            cursor.execute(
                f"GET {source_stage_path}/manifest.json.gz file://{temp_dir}/"
            )
            cursor.execute(
                f"GET {source_stage_path}/run_results.json.gz file://{temp_dir}/"
            )
            cursor.close()

            # Decompress files
            manifest_gz_path = temp_dir / "manifest.json.gz"
            run_results_gz_path = temp_dir / "run_results.json.gz"

            manifest_data = gzip.decompress(manifest_gz_path.read_bytes())
            run_results_data = gzip.decompress(run_results_gz_path.read_bytes())

            manifest_path = temp_dir / "manifest.json"
            run_results_path = temp_dir / "run_results.json"

            manifest_path.write_bytes(manifest_data)
            run_results_path.write_bytes(run_results_data)

            # Clean up gzipped files
            manifest_gz_path.unlink()
            run_results_gz_path.unlink()

            logger.info(
                f"Downloaded artifacts from Snowflake: {source_stage_path}/ "
                f"to {temp_dir}"
            )
            return {
                "manifest_path": str(manifest_path),
                "run_results_path": str(run_results_path),
            }
        except Exception as e:
            logger.error(f"Failed to download artifacts from Snowflake: {e}")
            return {}

    def list_versions(self) -> list:
        """List available artifact versions in Snowflake stage."""
        try:
            if self.snowflake_connection is None:
                logger.error("Snowflake connection not available for list")
                return []

            cursor = self.snowflake_connection.cursor()
            cursor.execute(f"LS {self.stage_path}/{self.prefix}/")
            results = cursor.fetchall()
            cursor.close()

            versions = [
                row[0].split("/")[-1]
                for row in results
                if row[0].split("/")[-1] not in ("", "latest")
            ]
            return sorted(versions, reverse=True)
        except Exception as e:
            logger.error(f"Failed to list Snowflake versions: {e}")
            return []


def get_artifact_storage(
    backend: str,
    target_name: str,
    project_name: str,
    config: dict,
    snowflake_connection=None,
) -> Optional[ArtifactStorage]:
    """Factory method to instantiate appropriate artifact storage backend.

    Args:
        backend: Storage backend type ('local', 's3', 'snowflake')
        target_name: dbt target name
        project_name: dbt project name
        config: Backend-specific configuration dict
        snowflake_connection: Optional Snowflake connection object

    Returns:
        ArtifactStorage instance or None if backend not supported
    """
    if backend == "local":
        local_path = config.get("local_path", "/tmp/xbt_artifacts")
        return LocalArtifactStorage(target_name, project_name, local_path)
    elif backend == "s3":
        bucket = config.get("bucket_name")
        region = config.get("aws_region", "us-east-1")
        if not bucket:
            logger.error("S3 backend requires 'bucket_name' in config")
            return None
        return S3ArtifactStorage(target_name, project_name, bucket, region)
    elif backend == "snowflake":
        stage_path = config.get("stage_path")
        if not stage_path:
            logger.error("Snowflake backend requires 'stage_path' in config")
            return None
        return SnowflakeArtifactStorage(
            target_name, project_name, stage_path, snowflake_connection
        )
    else:
        logger.error(f"Unknown artifact storage backend: {backend}")
        return None


def should_skip_upload(target_name: str, skip_patterns: list | None) -> bool:
    """Check if upload should be skipped based on target and patterns.

    Args:
        target_name: dbt target name
        skip_patterns: List of regex patterns or exact matches to skip

    Returns:
        True if target matches any skip pattern, False otherwise
    """
    if not skip_patterns:
        return False

    for pattern in skip_patterns:
        # Try exact match first
        if target_name == pattern:
            return True

        # Try regex match
        try:
            if re.match(pattern, target_name):
                return True
        except re.error:
            logger.warning(f"Invalid regex pattern in skip_patterns: {pattern}")
            continue

    return False
