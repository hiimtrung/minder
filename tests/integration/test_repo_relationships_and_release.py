"""Integration tests for cross-repo relationships and release asset consistency.
"""

from __future__ import annotations

from pathlib import Path

from minder.presentation.cli.utils.git import detect_branch_relationships
from minder.tools.repo_scanner import RepoScanner


def test_cross_repo_relationships_detected_and_in_payload(
    tmp_path: Path,
) -> None:
    repo_root = tmp_path / "repo"
    (repo_root / ".minder").mkdir(parents=True)
    (repo_root / ".gitmodules").write_text(
        '[submodule "vendor/other"]\n'
        "\tpath = vendor/other\n"
        "\turl = git@github.com:example/other.git\n"
        "\tbranch = release/1.0\n",
        encoding="utf-8",
    )
    (repo_root / ".minder" / "branch-topology.toml").write_text(
        "[[branch_relationships]]\n"
        'source_branch = "develop"\n'
        'target_repo_name = "sibling-service"\n'
        'target_repo_url = "git@github.com:example/sibling.git"\n'
        'target_branch = "develop"\n'
        'relation = "consumes"\n'
        'direction = "inbound"\n'
        "confidence = 0.9\n"
        "[branch_relationships.metadata]\n"
        'reason = "orders.created bus"\n',
        encoding="utf-8",
    )

    relationships = detect_branch_relationships(repo_root, "feature/sync")
    payload = RepoScanner.build_sync_payload(
        str(repo_root),
        branch="feature/sync",
        diff_base="origin/main",
        changed_files=[],
        deleted_files=[],
        branch_relationships=relationships,
    )

    assert payload["sync_metadata"]["branch_relationship_count"] == 2
    assert isinstance(payload["branch_relationships"], list)
    assert len(payload["branch_relationships"]) == 2

    target_names = {entry["target_repo_name"] for entry in payload["branch_relationships"]}
    assert target_names == {"other", "sibling-service"}

    submodule_entry = next(
        entry
        for entry in payload["branch_relationships"]
        if entry["target_repo_name"] == "other"
    )
    assert submodule_entry["metadata"]["source"] == "gitmodules"
    assert submodule_entry["target_branch"] == "release/1.0"

    override_entry = next(
        entry
        for entry in payload["branch_relationships"]
        if entry["target_repo_name"] == "sibling-service"
    )
    assert override_entry["metadata"]["source"] == "branch-topology.toml"
    assert override_entry["relation"] == "consumes"
    assert override_entry["direction"] == "inbound"


def test_release_assets_contain_cross_platform_installers() -> None:
    bash_installer = Path("scripts/release/install-minder-release.sh").read_text()
    powershell_installer = Path(
        "scripts/release/install-minder-release.ps1"
    ).read_text()
    release_workflow = Path(".github/workflows/release.yml").read_text()

    # Both installers carry placeholder tokens that the release workflow rewrites.
    for installer in (bash_installer, powershell_installer):
        assert "__REPO_OWNER__" in installer
        assert "__REPO_NAME__" in installer
        assert "__RELEASE_TAG__" in installer

    # Release workflow substitutes, renames, and attaches both installers.
    assert "install-minder-release.sh" in release_workflow
    assert "install-minder-release.ps1" in release_workflow
    assert (
        "install-minder-${{ needs.build-dist.outputs.release_tag }}.sh"
        in release_workflow
    )
    assert (
        "install-minder-${{ needs.build-dist.outputs.release_tag }}.ps1"
        in release_workflow
    )

    # PowerShell installer must use the argv form so Windows PowerShell 5.1 is safe.
    assert "& docker @composeArgs pull" in powershell_installer
    assert "& docker @composeArgs up -d" in powershell_installer


def test_production_guide_documents_both_install_paths() -> None:
    guide = Path("docs/guides/production-deployment.md").read_text()

    assert "install-minder-<tag>.sh" in guide
    assert "install-minder-<tag>.ps1" in guide
    assert "MINDER_INSTALL_DIR" in guide
    assert "MINDER_MODELS_DIR" in guide
    assert "minder update --component server" in guide
