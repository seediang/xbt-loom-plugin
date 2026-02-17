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
