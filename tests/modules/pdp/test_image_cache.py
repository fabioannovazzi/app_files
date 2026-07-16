from pathlib import Path

from modules.pdp.image_cache import build_image_cache, find_local_image


def _write_image(path: Path) -> None:
    path.write_bytes(b"test")


def test_find_local_image_supports_mixed_separators(tmp_path):
    root = tmp_path / "image_root"
    images_dir = root / "kiko_blush" / "images"
    images_dir.mkdir(parents=True)

    underscore_parent = images_dir / "43658_hero.webp"
    underscore_variant = images_dir / "43658_20551_hero.webp"
    hyphen_variant = images_dir / "43658-20552-hero-2.jpg"

    for path in (underscore_parent, underscore_variant, hyphen_variant):
        _write_image(path)

    cache = build_image_cache(root)

    stored = cache.get("43658")
    assert stored is not None
    stored_names = {item.path.name for item in stored}
    assert stored_names == {
        underscore_parent.name,
        underscore_variant.name,
        hyphen_variant.name,
    }

    parent_path = find_local_image(cache, "43658")
    assert parent_path is not None
    assert parent_path.name in stored_names

    variant_path = find_local_image(cache, "43658", "20551")
    assert variant_path is not None
    assert variant_path.name == underscore_variant.name

    hyphenated_variant = find_local_image(cache, "43658", "20552")
    assert hyphenated_variant is not None
    assert hyphenated_variant.name == hyphen_variant.name
