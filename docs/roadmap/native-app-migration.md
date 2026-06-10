# Native App Migration — Docker → Tauri + Turbovec

**Status:** Phase 1–3 Complete (Phase 4 docs cleanup done inline)  
**Started:** 2026-05-25  
**Goal:** Replace Docker-based deployment with a native macOS/Linux app. Eliminate the performance overhead of Docker virtualization. Bundle minder-server as a native binary managed by a Tauri desktop shell.

---

## Problem

The current production deployment uses four Docker containers:

| Container | Role |
|-----------|------|
| `minder-gateway` (Caddy) | Reverse proxy / TLS |
| `minder-api` (Python FastAPI) | Application server |
| `minder-dashboard` (Astro static) | Frontend assets |
| `minder-qdrant` (Qdrant) | Vector DB + operational store |

Docker virtualization introduces CPU and I/O overhead that makes local AI inference noticeably slower. Qdrant requires a separate long-running process even when the server is idle. First-run setup requires Docker knowledge.

---

## Target Architecture

```
Tauri Desktop App (macOS .app / Linux .AppImage)
├── WebView  ──────────────────────► http://localhost:8800/dashboard
└── Rust backend
    └── spawns & manages: minder-server (PyInstaller binary)
                          ├── FastAPI (serves dashboard + API)
                          ├── SQLite (operational/relational data)
                          └── Turbovec (embedded vector search)
```

No Docker. No Caddy. No separate Qdrant process.  
Single `.dmg` / `.AppImage` to install.

---

## Migration Phases

### Phase 1 — Drop Qdrant, switch to native stores ✅ DONE

**Goal:** Remove all Qdrant dependencies from the default stack.

#### Tasks

| ID | Task | Status |
|----|------|--------|
| T1.1 | Change `relational_store.provider` default to `sqlite` | ✅ Done |
| T1.2 | Change `vector_store.provider` default to `turbovec` | ✅ Done |
| T1.3 | Implement Turbovec vector store (`src/minder/store/turbovec/`) | ✅ Done |
| T1.4 | Add `turbovec` to `server` extra; move `qdrant-client` to optional `qdrant` extra | ✅ Done |
| T1.5 | Update `config.py`: add `TurbovecConfig`, update defaults | ✅ Done |
| T1.6 | Update `providers.py`: Turbovec branch in `build_vector_store()` | ✅ Done |
| T1.7 | Update `minder.toml` defaults | ✅ Done |
| T1.8 | Guard Qdrant package imports; add `pytest.importorskip` to Qdrant tests | ✅ Done |
| T1.9 | Add `native-install` and `native-run` Makefile targets | ✅ Done |

**Result:** 506 tests pass, 2 Qdrant tests self-skip, mypy clean on 201 files.

**Key implementation note:** Turbovec uses `IdMapIndex` (4-bit quantized ANN). All blocking index calls are wrapped with `asyncio.to_thread()` so the FastAPI event loop is never blocked. Index stored at `~/.minder/data/vectors.tvim`.

---

### Phase 2 — Native server improvements ✅ DONE

**Goal:** Ensure the Python server starts cleanly on a bare macOS/Linux system without Docker.

#### Tasks

| ID | Task | Status |
|----|------|--------|
| T2.1 | Auto-create `~/.minder/data/` on first run | ✅ Done (providers.py + TurbovecStore) |
| T2.2 | Startup health check log (which stores are active) | ✅ Done (server.py already logs store/transport) |
| T2.3 | PyInstaller spec file (`minder-server.spec`) | ✅ Done |
| T2.4 | Add `make native-install`, `make native-run`, `make bundle` targets | ✅ Done |

---

### Phase 3 — Tauri App Shell ✅ DONE

**Goal:** Wrap the Python server in a Tauri desktop app with native packaging.

#### Tasks

| ID | Task | Status |
|----|------|--------|
| T3.1 | Initialize Tauri project (`src-tauri/`) | ✅ Done |
| T3.2 | Configure Python binary as Tauri sidecar (`bundle.externalBin`) | ✅ Done |
| T3.3 | Implement Rust sidecar manager (spawn on start, kill on close, health-wait) | ✅ Done (`lib.rs`) |
| T3.4 | Splash screen HTML while server starts; navigate to dashboard on ready | ✅ Done (`splash/index.html`) |
| T3.5 | macOS packaging: `.dmg` via `tauri build` | ✅ Ready (`make app-build`) |
| T3.6 | Linux packaging: `.deb` + `.AppImage` via `tauri build` | ✅ Ready (`make app-build`) |
| T3.7 | Add `make app-dev`, `make app-build` targets | ✅ Done |

**Sidecar note:** In development, `src-tauri/binaries/minder-server-<triple>` is a shell script
that runs `uv run python -m minder.server`. For production distribution, run `make bundle`
to replace it with a PyInstaller binary (no uv/Python needed at runtime).

---

### Phase 4 — Cleanup ✅ DONE

| ID | Task | Status |
|----|------|--------|
| T4.1 | `docs/guides/local-setup.md` — updated to native-first setup | ✅ Done |
| T4.2 | `.gitignore` — Tauri artifacts excluded; dev stubs tracked | ✅ Done |
| T4.3 | CI native build matrix | ⬜ Future work (GitHub Actions) |

---

## File Map

| File / Directory | Role |
|---|---|
| `src/minder/store/turbovec/` | Turbovec vector store (new, replaces Qdrant) |
| `src/minder/store/qdrant/` | Qdrant store (optional, `qdrant` extra, legacy) |
| `src/minder/config.py` | Added `TurbovecConfig`; `relational_store.provider=sqlite`, `vector_store.provider=turbovec` |
| `src/minder/bootstrap/providers.py` | Turbovec + SQLite branches; Qdrant kept as optional |
| `pyproject.toml` | `turbovec` in `server`; `qdrant-client` in optional `qdrant` extra |
| `minder.toml` | Runtime defaults: turbovec, sqlite |
| `minder-server.spec` | PyInstaller spec for `make bundle` |
| `src-tauri/` | Tauri desktop app shell |
| `src-tauri/src/lib.rs` | Rust: sidecar spawn, TCP health-wait, window navigation |
| `src-tauri/tauri.conf.json` | Tauri app config (window, bundle, sidecar) |
| `src-tauri/splash/index.html` | Loading screen shown while server starts |
| `src-tauri/binaries/minder-server-*` | Sidecar binary (dev: shell script stub; prod: PyInstaller) |
| `Makefile` | `native-install`, `native-run`, `bundle`, `app-dev`, `app-build` |
| `docs/guides/local-setup.md` | Updated: native-first setup, no Docker required |

---

## Design Decisions

| Decision | Choice | Reason |
|---|---|---|
| Vector DB | Turbovec | Embedded, file-based, 4-bit quantized ANN (`IdMapIndex`); same IVectorStore interface |
| Operational store | SQLite | Already implemented (1386-line RelationalStore); zero new code |
| Desktop shell | Tauri | System WebView (~5 MB binary) vs Electron (~120 MB + Chromium) |
| Python packaging | PyInstaller | Single binary = clean Tauri `externalBin` sidecar; no uv/venv at runtime |
| Gateway | Removed | FastAPI serves Astro static files directly; Tauri WebView connects to localhost |
| Qdrant | Optional (`qdrant` extra) | Keep for users who explicitly configure it; not installed by default |
