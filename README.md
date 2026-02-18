## xbt-loom-plugin

An xbt plugin that auto-generates `dbt_loom.config.yml` from `dependencies.yml`
before dbt runs, with support for templating and env var substitution.

## dbt_loom.config.template.yml

The auto-configure plugin can render a template file to generate
`dbt_loom.config.yml`. If a template is found, it is rendered with Jinja2 and
environment variable substitution, then written to the project.

Search order:
1. `{project_dir}/dbt_loom.config.template.yml`
2. `{project_dir.parent}/dbt_loom.config.template.yml`
3. `{workspace_root}/dbt_loom.config.template.yml`

Template context variables:
- `project_root`: Root directory of the current dbt project
- `profiles_dir`: Resolved profiles directory (empty string if not resolved)
- `project_name`: Name from `dbt_project.yml`
- `upstream_projects`: List of upstream project dicts with keys:
	- `name`
	- `upstream_project`
	- `manifest_path` (relative)
	- `manifest_path_abs` (absolute)
	- `manifest_type`
	- `config` (optional)
	- `excluded_packages` (optional)

Environment variables are expanded after Jinja2 rendering. Supported formats:
`${VAR_NAME}` and `$VAR_NAME`.

Example template:

```yaml
manifests:
{% for project in upstream_projects %}
	- name: {{ project.name }}
		type: {{ project.manifest_type | default('file') }}
		config:
			path: {{ project.manifest_path }}
{% endfor %}
```

If no template is found, a default file-based configuration is generated from
`dependencies.yml`.

## Artifact storage configuration

xbt-loom-plugin supports uploading and downloading dbt artifacts (like
`manifest.json`) to various storage backends for sharing between projects.

### Configuration precedence

Artifact storage settings are resolved in the following order (highest to
lowest):

1. **Environment variables** (highest priority)
2. **~/.dbt/xbt_loom_artifacts.yml** configuration file
3. **Default values** (lowest priority)

**Note**: The `pyproject.toml` file is NOT used for artifact configuration.
Configuration should be set at the system/user level, not in project files.

### Configuration file format

Create a file at `~/.dbt/xbt_loom_artifacts.yml` (optional):

```yaml
backend: s3
bucket_name: my-artifacts-bucket
aws_region: us-west-2
upload_skip_patterns:
  - dev
  - test
```

Supported settings:

- `backend`: Storage backend type (`local`, `s3`, or `snowflake`)
- `local_path`: Local directory for artifact storage (default:
	`~/.xbt/xbt_loom/artifacts`)
- `bucket_name`: S3 bucket name (required for S3 backend)
- `aws_region`: AWS region for S3 (default: `us-east-1`)
- `stage_path`: Snowflake stage path (required for Snowflake backend, e.g.,
	`@my_database.my_schema.my_stage/artifacts`)
- `upload_skip_patterns`: List of target names to skip during artifact upload

### Environment variables

All configuration values can be overridden with environment variables:

- `XBT_LOOM_ARTIFACT_BACKEND`: Storage backend type
- `XBT_LOOM_ARTIFACT_LOCAL_PATH`: Local directory path
- `XBT_LOOM_ARTIFACT_S3_BUCKET`: S3 bucket name
- `XBT_LOOM_ARTIFACT_AWS_REGION`: AWS region
- `XBT_LOOM_ARTIFACT_SNOWFLAKE_STAGE`: Snowflake stage path
- `XBT_LOOM_ARTIFACT_TARGET`: Override dbt target for artifact resolution

### Default values

When no configuration file or environment variables are set:

- `backend`: `local`
- `local_path`: `~/.xbt/xbt_loom/artifacts`
- `aws_region`: `us-east-1`
- `bucket_name`: `None`
- `stage_path`: `None`
- `upload_skip_patterns`: `[]`

## Validation behavior

Configuration generation is strict and fail-fast:

- `dependencies.yml` must be a YAML mapping.
- `projects` must be a list.
- each project entry must include a non-empty `name` and valid optional fields
	(`type`, `config`, `excluded_packages`).
- non-`file` manifest types must provide `config`.

For template-based generation, rendered YAML is validated before writing:

- top-level `manifests` must exist and be a list.
- each manifest must include `name`, `type`, and mapping `config`.
- manifest type and required config fields are validated with the same rules as
	default generation.

String fields are rendered with Jinja2 and environment-variable substitution.
Non-string config values (for example booleans, integers, lists, and nested
mappings) keep their native YAML types.
