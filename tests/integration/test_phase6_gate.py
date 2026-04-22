"""Phase 6 acceptance gate.

This gate verifies the shipped Phase 6 surface:

- CLI + repo scanner auto-detect cross-repo ``branch_relationships`` from
  ``.gitmodules`` and an optional ``.minder/branch-topology.toml`` override
  (P6-T01).
- Release assets include a bash installer *and* a PowerShell installer with
  placeholder tokens that the release workflow substitutes at publish time
  (P6-T06).
- Release workflow publishes both installers under the tagged file names the
  update flow expects (P6-T07).
- The production deployment guide documents both bash and PowerShell install
  one-liners (P6-T07).
"""

from __future__ import annotations

from pathlib import Path

from minder import cli
from minder.tools.repo_scanner import RepoScanner


def test_phase6_gate_branch_relationships_detected_and_in_payload(
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

    relationships = cli._detect_branch_relationships(repo_root, "feature/sync")
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


def test_phase6_gate_release_assets_have_cross_platform_installers() -> None:
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


def test_phase6_gate_production_guide_documents_both_install_paths() -> None:
    guide = Path("docs/guides/production-deployment.md").read_text()

    assert "install-minder-<tag>.sh" in guide
    assert "install-minder-<tag>.ps1" in guide
    assert "MINDER_INSTALL_DIR" in guide
    assert "MINDER_MODELS_DIR" in guide
    assert "minder update --component server" in guide
