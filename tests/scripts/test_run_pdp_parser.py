from __future__ import annotations

import argparse
import json
from pathlib import Path

import polars as pl

from modules.pdp.profile_loader import load_profile
from scripts.run_pdp_parser import (
    ProfileRun,
    _export_results,
    _load_links_for_retailer,
    _runs_from_args,
)


def test_load_links_for_retailer_reads_and_filters_categories(tmp_path: Path) -> None:
    links_path = tmp_path / "links.json"
    links_path.write_text(
        json.dumps(
            {
                "ulta": {
                    "lipstick": [
                        "https://www.ulta.com/p/a-pimprod1",
                        "https://www.ulta.com/p/a-pimprod1",
                    ],
                    "lip_gloss": ["https://www.ulta.com/p/b-pimprod2"],
                }
            }
        ),
        encoding="utf-8",
    )

    links = _load_links_for_retailer(
        links_path,
        retailer="ulta",
        categories={"lipstick"},
    )

    assert links == {
        "lipstick": ["https://www.ulta.com/p/a-pimprod1"],
    }


def test_runs_from_args_uses_links_before_discovery(
    monkeypatch, tmp_path: Path
) -> None:
    links_path = tmp_path / "links.json"
    links_path.write_text(
        json.dumps(
            {
                "ulta": {
                    "lipstick": ["https://www.ulta.com/p/from-links-pimprod1"],
                }
            }
        ),
        encoding="utf-8",
    )

    profile = load_profile("ulta_lipstick")
    monkeypatch.setattr(
        "scripts.run_pdp_parser._load_retailer_profiles",
        lambda retailer: [profile],
    )
    monkeypatch.setattr(
        "scripts.run_pdp_parser._discover_for_profile",
        lambda profile, *, max_pages: [
            "https://www.ulta.com/p/from-discovery-pimprod2"
        ],
    )

    args = argparse.Namespace(
        profile=None,
        urls=(),
        urls_file=None,
        retailer="ulta",
        categories=["lipstick"],
        links_path=links_path,
        max_pages=50,
        output_dir=Path("data/pdp/cli"),
        no_evidence=False,
        overwrite=False,
        reviews_only=False,
        locale="en-us",
        human_pace=False,
        only_missing_images=False,
    )

    runs = _runs_from_args(args)

    assert len(runs) == 1
    assert runs[0].profile.profile_name == "ulta_lipstick"
    assert runs[0].urls == ["https://www.ulta.com/p/from-links-pimprod1"]


def test_load_retailer_profiles_finds_saloncentric_profile() -> None:
    from scripts.run_pdp_parser import _load_retailer_profiles

    profiles = _load_retailer_profiles("saloncentric")

    assert profiles
    assert any(profile.profile_name == "saloncentric_permanent" for profile in profiles)


def test_export_results_removes_legacy_parquet_snapshots(tmp_path: Path) -> None:
    profile = load_profile("ulta_lipstick")
    run = ProfileRun(profile=profile, urls=[])
    profile_dir = tmp_path / profile.profile_name
    profile_dir.mkdir(parents=True)
    stale_parents = profile_dir / "parents.parquet"
    stale_variants = profile_dir / "variants.parquet"
    stale_parents.write_bytes(b"legacy")
    stale_variants.write_bytes(b"legacy")
    parents_df = pl.DataFrame(
        {
            "parent_product_id": ["p1"],
            "pdp_url": ["https://www.ulta.com/p/example-pimprod1"],
        }
    )
    variants_df = pl.DataFrame(
        {
            "parent_product_id": ["p1"],
            "variant_id": ["v1"],
            "price": [12.0],
        }
    )

    _export_results(
        run,
        parents_df,
        variants_df,
        {"parsed": 1},
        tmp_path,
        overwrite=False,
    )

    assert (profile_dir / "parents.csv").exists()
    assert (profile_dir / "variants.csv").exists()
    assert not stale_parents.exists()
    assert not stale_variants.exists()
