from __future__ import annotations

import zipfile
from pathlib import Path

import polars as pl

from modules.pdp import face_mapping_pack
from modules.pdp.face_mapping_pack import (
    _build_issue_examples,
    _materialize_pack_image,
    _package_output_dir,
    _package_zip_path,
    _prepare_package_output_dir,
    zip_face_mapping_review_pack,
)


def test_build_issue_examples_limits_per_issue() -> None:
    frame = pl.DataFrame(
        {
            "mapped_category_key": ["color_correct"] * 6,
            "filter_family": ["spf"] * 6,
            "verdict": [
                "mismatch",
                "mismatch",
                "mismatch",
                "mismatch",
                "mismatch",
                "exact_match",
            ],
            "parent_product_id": ["a", "b", "c", "d", "e", "f"],
            "product_name": ["A", "B", "C", "D", "E", "F"],
        }
    )

    out = _build_issue_examples(frame, per_issue_limit=3)

    assert out.select("parent_product_id").to_series().to_list() == ["a", "b", "c"]


def test_zip_face_mapping_review_pack_includes_expected_files(tmp_path: Path) -> None:
    pack_dir = tmp_path / "pack"
    images_dir = pack_dir / "images"
    images_dir.mkdir(parents=True)
    for name in [
        "summary.json",
        "pack_manifest.json",
        "prompt_for_pro.txt",
        "category_overview.csv",
        "priority_issue_matrix.csv",
        "product_filter_matrix.csv",
        "image_index.csv",
    ]:
        (pack_dir / name).write_text("x", encoding="utf-8")
    (images_dir / "sample.png").write_text("img", encoding="utf-8")

    zip_path = zip_face_mapping_review_pack(pack_dir)

    assert zip_path.exists()
    with zipfile.ZipFile(zip_path) as zf:
        names = set(zf.namelist())
    assert "pack/summary.json" in names
    assert "pack/prompt_for_pro.txt" in names
    assert "pack/images/sample.png" in names


def test_face_mapping_pack_uses_stable_retailer_package_layout(tmp_path: Path) -> None:
    output_dir = _package_output_dir(
        tmp_path,
        retailer="ulta",
        package_key="face-mapping-review",
    )

    assert output_dir == tmp_path / "ulta" / "face_mapping_review"
    assert (
        _package_zip_path(output_dir) == tmp_path / "ulta" / "face_mapping_review.zip"
    )


def test_face_mapping_pack_prepares_clean_stable_folder(tmp_path: Path) -> None:
    stale_path = tmp_path / "ulta" / "face_mapping_review" / "old.csv"
    stale_zip_path = tmp_path / "ulta" / "face_mapping_review.zip"
    stale_path.parent.mkdir(parents=True)
    stale_path.write_text("old", encoding="utf-8")
    stale_zip_path.write_text("old zip", encoding="utf-8")

    output_dir = _prepare_package_output_dir(
        tmp_path,
        retailer="ulta",
        package_key="face_mapping_review",
    )

    assert output_dir == tmp_path / "ulta" / "face_mapping_review"
    assert output_dir.exists()
    assert not stale_path.exists()
    assert not stale_zip_path.exists()


def test_materialize_pack_image_prefers_local_cli_image(
    tmp_path: Path,
    monkeypatch,
) -> None:
    cli_root = tmp_path / "cli"
    local_image = (
        cli_root / "ulta_bb_cc_creams" / "images" / "pimprod123_77000001_hero.png"
    )
    local_image.parent.mkdir(parents=True)
    local_image.write_bytes(b"img")

    monkeypatch.setattr(
        face_mapping_pack,
        "_download_image",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("network download should not run")
        ),
    )
    monkeypatch.setattr(
        face_mapping_pack,
        "_fetch_og_image_url",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("og:image fallback should not run")
        ),
    )

    result = _materialize_pack_image(
        output_dir=tmp_path / "pack",
        parent_product_id="pimprod123",
        hero_image_url="https://cdn.example.com/hero.png",
        pdp_url="https://www.ulta.com/p/example",
        cli_root=cli_root,
    )

    assert result["pack_image_source"] == "local_cli_image"
    assert result["pack_image_path"] is not None
    copied = Path(result["pack_image_path"])
    assert copied.exists()
    assert copied.read_bytes() == b"img"
