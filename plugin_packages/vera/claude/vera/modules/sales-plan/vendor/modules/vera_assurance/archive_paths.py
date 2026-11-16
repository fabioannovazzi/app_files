"""Resolve product-folder casing without changing retained evidence bytes."""

from __future__ import annotations

from pathlib import Path

__all__ = [
    "PRODUCT_DIRECTORIES",
    "product_root",
    "archive_path",
    "ensure_project_layout",
    "plan_project_layout",
]
PRODUCT_DIRECTORIES = ("vera", "lucia", "clara")


def product_root(root: Path, product: str) -> Path:
    """Resolve one real product directory; reject ambiguous or redirected areas."""
    name = product.casefold()
    if name not in PRODUCT_DIRECTORIES:
        raise ValueError("Unknown Archive product directory")
    matches = (
        [p for p in root.iterdir() if p.name.casefold() == name]
        if root.exists()
        else []
    )
    if len(matches) > 1:
        raise ValueError(
            "Archive product folders differ only by case; preserve both and resolve the collision"
        )
    if matches:
        path = matches[0]
        if path.is_symlink() or not path.is_dir():
            raise ValueError("Archive product folder must be a real directory")
        return path
    return root / name


def archive_path(root: Path, relative: str | Path) -> Path:
    """Map legacy product spelling to its actual folder, retaining all other parts."""
    relative = Path(relative)
    if relative.is_absolute() or ".." in relative.parts:
        raise ValueError("Archive path must remain relative to its project")
    if relative.parts and relative.parts[0].casefold() in PRODUCT_DIRECTORIES:
        return product_root(root, relative.parts[0]).joinpath(*relative.parts[1:])
    return root / relative


def plan_project_layout(root: Path) -> dict[str, Path]:
    """Preflight every area before creating or renaming any folder."""
    if root.is_symlink() or not root.is_dir():
        raise ValueError("Archive project must be a real directory")
    areas = {name: product_root(root, name) for name in PRODUCT_DIRECTORIES}
    for path in areas.values():
        collection = path / "engagements"
        if collection.is_symlink() or (collection.exists() and not collection.is_dir()):
            raise ValueError("Archive engagement collection must be a real directory")
    return areas


def ensure_project_layout(root: Path) -> dict[str, str]:
    """Materialize all three lowercase areas, preserving every existing file byte."""
    areas = plan_project_layout(root)
    result = {}
    for name, current in areas.items():
        target = root / name
        if current.exists() and current.name != name:
            current.rename(target)
        target.mkdir(mode=0o700, exist_ok=True)
        if product_root(root, name).name != name:
            raise ValueError("Archive product folder casing could not be normalized")
        (target / "engagements").mkdir(mode=0o700, exist_ok=True)
        result[name] = str(target)
    return result
