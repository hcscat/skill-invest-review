# Privacy and publication policy

This package contains reusable, read-only investment-review instructions and a
Toss-specific adapter. Keep personal holdings, credentials and device settings in
the user's private workspace.

## Local AI instructions

Treat every project AGENTS.md and AGENTS.override.md, including nested copies,
as local-only guidance. Maintain existing content, but exclude these files from
staging, commits, pushes, releases and packages. Inclusion requires the user's
explicit request for the specific file in the specific external action. A general
documentation, commit, deployment or publishing request is not that permission.

Each repository must carry the basename exclusions AGENTS.md and
AGENTS.override.md in its shared .gitignore. A parent repository's rules and
machine-local exclusions do not protect a separate checkout on another device.
Ignore rules do not untrack files or control package contents. Inspect staged
paths, outgoing commits and the actual artifact manifest before external writes.
If tracked or previously published guidance conflicts with the policy, preserve
the content, report the conflict and prepare a scoped remedy. Do not automatically
delete files, rewrite history or force-push.

## Private runtime state

Keep credentials, filled-in configuration, workspace mappings, private prompts,
logs, databases, backups, account identifiers, screenshots and operational reports
local. Share only sanitized templates and reusable code. Never paste credentials
or raw sensitive matches into audit output.

<!-- Update this list when package files change; do not import local AGENTS content. -->

The package file allowlist is README.md, SKILL.md, agents/openai.yaml,
references/source-fallback.md, references/data-quality.md,
scripts/toss_openapi_check.py, tests/test_toss_openapi_check.py, .gitignore,
.gitattributes and SECURITY.md. Tests contain only synthetic data and run without
credentials or network access. Review and update this list before adding any new
public file. The portfolio/SQLite benchmark is not part of the package.

Adapter diagnostics suppress raw error bodies and filesystem exception details.
Help/import does not load credentials. Runtime workspace discovery is limited to
an explicit environment value, the current marked workspace or the adapter's
package root; it does not search unrelated folders. The HTTP helper permits GET
and OAuth token issuance only and does not follow redirects carrying credentials.
CLI session guards are not a security boundary for arbitrary imported Python code.

The .gitattributes file excludes local guidance and private state from Git
archives. Before using any other packaging tool, configure its exclusions and
inspect the files it actually emits. Git ignore and archive attributes alone do
not govern wheel, npm, container or custom archive contents.

## Another device

When setting up an AI tool on a new device, merge this sanitized policy into its
supported global instruction file. For Codex this is AGENTS.md under CODEX_HOME,
or under the user's home .codex directory when CODEX_HOME is unset. Preserve
existing guidance. Do not automatically copy machine-specific instruction
content, credentials or private configuration. A clone transfers committed
.gitignore rules, not global AI instructions; verify configuration before claiming
the other device is ready.

This policy document is shareable. It does not authorize publishing project
AGENTS files.
