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
