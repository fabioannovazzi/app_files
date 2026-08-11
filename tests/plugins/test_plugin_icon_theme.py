from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PLUGIN_ROOT = ROOT / "plugins"
THEME_MARKER = "mparanza-plugin-icon-v1"


def test_all_plugin_icons_use_shared_theme_marker() -> None:
    icon_paths = sorted(PLUGIN_ROOT.glob("*/assets/icon.svg"))

    assert icon_paths
    for path in icon_paths:
        svg = path.read_text(encoding="utf-8")
        assert f'data-theme="{THEME_MARKER}"' in svg, path
        assert 'viewBox="0 0 64 64"' in svg, path
        if path.parent.parent.name in {"clara", "lucia", "vera"}:
            assert 'fill="#002060"' in svg, path
            assert 'fill="#171816"' not in svg, path
            assert all(color in svg for color in ("#0070C0", "#00B0F0", "#FFFFFF")), path
        else:
            assert 'fill="#171816"' in svg, path


def test_plugin_icons_are_not_duplicated() -> None:
    icon_paths = sorted(PLUGIN_ROOT.glob("*/assets/icon.svg"))
    contents = [path.read_text(encoding="utf-8") for path in icon_paths]

    assert len(contents) == len(set(contents))


def test_lucia_icon_is_a_human_companion() -> None:
    svg = (PLUGIN_ROOT / "lucia" / "assets" / "icon.svg").read_text(
        encoding="utf-8"
    )

    assert '<circle cx="32" cy="21" r="7.5" fill="#FFFFFF"/>' in svg
    assert 'd="M15 51c1.8-11.5 8.2-17 17-17s15.2 5.5 17 17z"' in svg
    assert 'd="M15 13h29l8 9v31H15z"' not in svg
