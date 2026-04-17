# Minder CLI Guide

Use `minder` as the repo-local edge extractor for fast graph sync.

## Install

Preferred install methods:

```bash
uv tool install minder
```

Or:

```bash
pipx install minder
```

Upgrade later with:

```bash
uv tool upgrade minder
```

Or let Minder manage both the check and upgrade flow:

```bash
minder check-update --component cli
minder self-update --component cli
```

## Login

Store the client key and default server URL locally:

```bash
minder login \
  --client-key mkc_your_client_key \
  --server-url http://localhost:8800/sse
```

This writes `~/.minder/client.json` by default.

## Install MCP Config

Install MCP config files into the current workspace:

```bash
minder install-mcp
```

Install a full repo-local IDE bootstrap instead:

```bash
minder install-ide
```

This repo-local bootstrap currently:

- writes target-specific MCP config into `.vscode/`, `.cursor/`, and/or `.claude/`
- installs supported instruction files for VS Code, Cursor, and Claude Code
- installs a Claude Code repo agent file
- patches existing instruction files in place using Minder-managed blocks
- updates local `.gitignore` so generated MCP config and `.minder/` metadata do not get committed accidentally

Remove the repo-local bootstrap later with:

```bash
minder uninstall-ide
```

Install into user-level config locations instead:

```bash
minder install-mcp --global
```

Supported targets:

- `vscode`
- `cursor`
- `claude-code`

Select one or more targets explicitly:

```bash
minder install-mcp --target vscode --target cursor
```

The same target selection works for repo-local IDE bootstrap:

```bash
minder install-ide --target vscode --target claude-code
```

Remove the generated entries later with:

```bash
minder uninstall-mcp
```

Or globally:

```bash
minder uninstall-mcp --global
```

## Sync Repository Metadata

From any directory inside a git repository:

```bash
minder sync
```

The CLI will:

- resolve or create the matching repository record on the server when `--repo-id` is omitted
- use the repository `origin` remote as the canonical identity for that resolution, normalized to SSH form
- detect the git repository root
- discover the current branch
- compute changed and deleted files from git diff
- extract structural metadata from supported source and document files
- push the payload to `POST /v1/client/repositories/{repo_id}/graph-sync`

When `--repo-id` is omitted, the current git repository must have an `origin` remote configured. Minder normalizes HTTPS and `ssh://` remotes into canonical SSH form such as `git@github.com:owner/repo.git` before resolving the repository on the server.

If you already know the repository UUID, you can still pin it explicitly:

```bash
minder sync --repo-id 11111111-1111-1111-1111-111111111111
```

Use a specific base ref for the delta:

```bash
minder sync \
  --diff-base origin/main
```

Preview the payload without sending it:

```bash
minder sync --dry-run
```

By default, `minder sync` also checks PyPI for a newer published CLI version and prints an upgrade hint when one exists.

Disable that check for air-gapped or tightly controlled environments:

```bash
minder sync --skip-upgrade-check
```

## Check Updates

Check both the installed CLI and the local server deployment at once:

```bash
minder check-update
```

Check only one component:

```bash
minder check-update --component cli
minder check-update --component server
```

If the server release lives outside the default `~/.minder/current` or `~/.minder/releases/*` locations, point the CLI at that deployment explicitly:

```bash
minder check-update --component server --install-dir ~/.minder/releases/v0.1.0
```

## Self Update

Upgrade the CLI in place:

```bash
minder self-update --component cli
```

Choose a specific package manager if your environment is pinned to one tool:

```bash
minder self-update --component cli --manager pipx
```

Upgrade a local server deployment in place by reusing the published GitHub release installer for the newest tag:

```bash
minder self-update --component server
```

Or target a specific deployment directory:

```bash
minder self-update --component server --install-dir ~/.minder/current
```

The server self-update flow preserves the current deployment directory plus key runtime env values such as `MINDER_MODELS_DIR`, `MINDER_PORT`, and `MILVUS_PORT`, then prints rollback guidance for the previous release.

## Supported Extraction Coverage

Current extraction coverage includes:

- Python
- JavaScript and TypeScript
- Java
- Go
- Rust
- Markdown
- JSON, TOML, YAML, and text/config metadata

The payload also carries deleted-file tombstones so the server can prune file-scoped graph nodes.

For modified files, the server also refreshes file-scoped graph nodes by `path` before applying the new payload, which prevents removed symbols and routes from lingering after a resync.
