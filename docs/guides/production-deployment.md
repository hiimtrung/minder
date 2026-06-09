# Production Deployment Guide

Minder is distributed as a **native desktop app** (Tauri) for macOS and Linux.
It bundles the Python server as a sidecar — no Docker, no external services required.

For server-side headless deployments (CI, self-hosted server), the Python server
can also run standalone with `uv` or as a PyInstaller binary.

---

## Option 1 — Tauri Desktop App (Recommended)

### Build

```bash
make native-install   # install Python deps + build dashboard
make bundle           # package Python server via PyInstaller
make app-build        # build native app (Tauri)
```

Outputs:
- **macOS**: `src-tauri/target/release/bundle/dmg/Minder_*.dmg`
- **Linux**: `src-tauri/target/release/bundle/deb/minder_*.deb` and `.AppImage`

### Install

**macOS:**

```bash
open "src-tauri/target/release/bundle/dmg/Minder_*.dmg"
# Drag Minder.app to /Applications
```

**Linux (Debian/Ubuntu):**

```bash
sudo dpkg -i src-tauri/target/release/bundle/deb/minder_*.deb
minder-app
```

**Linux (AppImage):**

```bash
chmod +x Minder_*.AppImage
./Minder_*.AppImage
```

### First Run

The app starts the Python server automatically (sidecar mode), shows a loading screen,
then navigates to the dashboard at `http://localhost:8800/dashboard`.

Data is stored in `~/.minder/data/`. Models download automatically on first boot (~4 GB).

---

## Option 2 — Standalone Python Server (Headless)

For server deployments (no GUI required).

### Install via uv

```bash
uv tool install minder-cli
```

Or from the repo:

```bash
uv sync --extra server
```

### Run

```bash
uv run python -m minder.server
```

The server starts on port `8800` by default. Serve it behind a reverse proxy (nginx, Caddy)
for production TLS termination.

### systemd Service (Linux)

Create `/etc/systemd/system/minder.service`:

```ini
[Unit]
Description=Minder MCP Server
After=network.target

[Service]
Type=simple
User=minder
WorkingDirectory=/opt/minder
ExecStart=uv run python -m minder.server
Restart=on-failure
RestartSec=5
Environment=MINDER_SERVER__HOST=0.0.0.0
Environment=MINDER_AUTH__JWT_SECRET=<your-secret>

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable --now minder
```

### launchd Service (macOS)

Create `~/Library/LaunchAgents/io.github.hiimtrung.minder.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>io.github.hiimtrung.minder</string>
  <key>ProgramArguments</key>
  <array>
    <string>/path/to/uv</string>
    <string>run</string>
    <string>python</string>
    <string>-m</string>
    <string>minder.server</string>
  </array>
  <key>WorkingDirectory</key><string>/opt/minder</string>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
</dict>
</plist>
```

```bash
launchctl load ~/Library/LaunchAgents/io.github.hiimtrung.minder.plist
```

---

## Configuration

All settings in `minder.toml` or environment variables (`MINDER_<SECTION>__<KEY>`):

```toml
[server]
host = "0.0.0.0"
port = 8800

[auth]
jwt_secret = "change-this-in-production"

[relational_store]
provider = "sqlite"
db_path = "~/.minder/data/minder.db"

[vector_store]
provider = "turbovec"

[turbovec]
db_path = "~/.minder/data/vectors.tvim"

[llm]
provider = "llama_cpp"
llama_cpp_model_repo = "ggml-org/gemma-4-E2B-it-GGUF"
llama_cpp_model_file = "gemma-4-E2B-it-Q8_0.gguf"
```

For PostgreSQL (larger deployments):

```toml
[relational_store]
provider = "postgresql"
uri = "postgresql+asyncpg://user:pass@host/minder"

[graph_store]
provider = "postgresql"
uri = "postgresql+asyncpg://user:pass@host/minder_graph"
```

---

## First-Run Admin Bootstrap

1. Start the server
2. Open `http://<host>:8800/dashboard/setup`
3. Enter email, username, display name
4. Copy the `mk_...` admin API key — shown once only

---

## Verify the MCP Server

```bash
curl -N http://localhost:8800/sse
```

Expected response:

```
event: endpoint
data: /messages/?session_id=...
```

---

## Recover a Lost Admin Key

```bash
uv run python scripts/reset_admin_api_key.py --username admin
```

---

## Upgrade

### Tauri App

Rebuild with the new source:

```bash
git pull
make native-install
make bundle
make app-build
```

Replace the app in `/Applications` or reinstall the `.deb`.

### Standalone Server

```bash
git pull
uv sync --extra server
systemctl restart minder
```
