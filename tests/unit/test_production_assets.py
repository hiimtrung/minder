"""
Tests verifying the native-app architecture artifacts are in place.

These replace the old Docker-centric checks. The target distribution is
a Tauri desktop app (src-tauri/) that bundles the Python server as a sidecar.
"""

from __future__ import annotations

from pathlib import Path


def test_tauri_project_structure_exists() -> None:
    assert Path("src-tauri/Cargo.toml").exists()
    assert Path("src-tauri/tauri.conf.json").exists()
    assert Path("src-tauri/src/main.rs").exists()
    assert Path("src-tauri/src/lib.rs").exists()
    assert Path("src-tauri/build.rs").exists()
    assert Path("src-tauri/capabilities/default.json").exists()
    assert Path("src-tauri/splash/index.html").exists()


def test_tauri_conf_has_correct_product_name_and_sidecar() -> None:
    import json
    conf = json.loads(Path("src-tauri/tauri.conf.json").read_text())
    assert conf["productName"] == "Minder"
    assert "externalBin" in conf["bundle"]
    assert any("minder-server" in b for b in conf["bundle"]["externalBin"])


def test_milvus_store_package_exists() -> None:
    assert Path("src/minder/store/milvus/__init__.py").exists()
    assert Path("src/minder/store/milvus/client.py").exists()
    assert Path("src/minder/store/milvus/vector_store.py").exists()


def test_turbovec_store_package_exists() -> None:
    assert Path("src/minder/store/turbovec/__init__.py").exists()
    assert Path("src/minder/store/turbovec/vector_store.py").exists()


def test_pyinstaller_spec_exists() -> None:
    assert Path("minder-server.spec").exists()
    spec = Path("minder-server.spec").read_text()
    assert "minder-server" in spec
    assert "pymilvus" in spec
    assert "turbovec" in spec
    # Verify native deployment: dashboard + config bundled in sidecar
    assert "native_datas" in spec
    assert "dashboard_dist" in spec
    assert "minder.toml" in spec


def test_native_makefile_targets_exist() -> None:
    makefile = Path("Makefile").read_text()
    assert "native-install:" in makefile
    assert "native-run:" in makefile
    assert "bundle:" in makefile
    assert "app-dev" in makefile
    assert "native-dev" in makefile
    assert "app-build" in makefile
    assert "native-build" in makefile


def test_model_bootstrap_handles_startup() -> None:
    bootstrap = Path("src/minder/infrastructure/model_bootstrap.py")
    assert bootstrap.exists()
    text = bootstrap.read_text()
    assert "ensure_models_available" in text
    assert "hf_hub_download" in text


def test_no_qdrant_store_package() -> None:
    # The Qdrant store has been removed — native stack uses Milvus Lite + SQLite.
    assert not Path("src/minder/store/qdrant").exists()
