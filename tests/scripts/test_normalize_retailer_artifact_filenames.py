from __future__ import annotations

from pathlib import Path

from scripts.normalize_retailer_artifact_filenames import main


def test_normalize_retailer_artifact_filenames_renames_legacy_csvs(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "cdp" / "chewy" / "run"
    run_dir.mkdir(parents=True)
    (run_dir / "listing_observations.csv").write_text("retailer\nchewy\n")
    (run_dir / "filter_observations.csv").write_text("retailer\nchewy\n")

    exit_code = main(["--roots", str(tmp_path / "cdp")])

    assert exit_code == 0
    assert not (run_dir / "listing_observations.csv").exists()
    assert not (run_dir / "filter_observations.csv").exists()
    assert (run_dir / "retailer_listing_observations.csv").exists()
    assert (run_dir / "retailer_filter_observations.csv").exists()


def test_normalize_retailer_artifact_filenames_removes_identical_duplicate(
    tmp_path: Path,
) -> None:
    run_dir = tmp_path / "cdp" / "chewy" / "run"
    run_dir.mkdir(parents=True)
    content = "retailer\nchewy\n"
    (run_dir / "filter_surfaces.csv").write_text(content)
    (run_dir / "retailer_filter_surfaces.csv").write_text(content)

    exit_code = main(["--roots", str(tmp_path / "cdp")])

    assert exit_code == 0
    assert not (run_dir / "filter_surfaces.csv").exists()
    assert (run_dir / "retailer_filter_surfaces.csv").read_text() == content
