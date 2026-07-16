from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

__all__ = ["build_contact_sheets", "main"]

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = (
    REPO_ROOT / "runs" / "chart_selection_manifest_rebuild" / "selection_manifest.json"
)
DEFAULT_OUTPUT_DIR = DEFAULT_MANIFEST.with_name("visual_review")
GALLERY_DIR = REPO_ROOT / "static" / "shared" / "png-gallery"


def _load_manifest(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Selection manifest must be a JSON object.")
    return payload


def build_contact_sheets(
    *,
    manifest_path: Path = DEFAULT_MANIFEST,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    items_per_sheet: int = 16,
    columns: int = 4,
) -> list[Path]:
    """Build labeled PNG contact sheets for visual manifest review."""

    manifest = _load_manifest(manifest_path)
    artifacts = manifest.get("artifacts")
    capabilities = manifest.get("capabilities")
    if not isinstance(artifacts, list) or not isinstance(capabilities, dict):
        raise ValueError("Selection manifest lacks artifacts or capabilities.")

    output_dir.mkdir(parents=True, exist_ok=True)
    font = ImageFont.load_default()
    thumb_width = 430
    thumb_height = 210
    label_height = 92
    padding = 10
    written: list[Path] = []

    for sheet_index in range((len(artifacts) + items_per_sheet - 1) // items_per_sheet):
        chunk = artifacts[sheet_index * items_per_sheet : (sheet_index + 1) * items_per_sheet]
        rows = (len(chunk) + columns - 1) // columns
        sheet = Image.new(
            "RGB",
            (
                columns * (thumb_width + padding) + padding,
                rows * (thumb_height + label_height + padding) + padding,
            ),
            "white",
        )
        draw = ImageDraw.Draw(sheet)

        for index, item in enumerate(chunk):
            if not isinstance(item, dict):
                continue
            column = index % columns
            row = index // columns
            x = padding + column * (thumb_width + padding)
            y = padding + row * (thumb_height + label_height + padding)

            image_name = str(item["output"])
            image_path = Path(image_name)
            if not image_path.is_absolute():
                image_path = GALLERY_DIR / image_name
            image = Image.open(image_path).convert("RGB")
            image.thumbnail((thumb_width, thumb_height), Image.Resampling.LANCZOS)
            image_x = x + (thumb_width - image.width) // 2
            image_y = y + (thumb_height - image.height) // 2
            sheet.paste(image, (image_x, image_y))
            draw.rectangle(
                [x, y, x + thumb_width, y + thumb_height],
                outline=(180, 180, 180),
            )

            capability_id = str(item["capability_id"])
            capability = capabilities[capability_id]
            label = "\n".join(
                [
                    f"{sheet_index * items_per_sheet + index + 1}. {item['label']}",
                    capability_id,
                    str(capability["selection_emphasis"]),
                ]
            )
            draw.multiline_text(
                (x, y + thumb_height + 8),
                label,
                fill=(0, 0, 0),
                font=font,
                spacing=4,
            )

        output_path = output_dir / f"contact_sheet_{sheet_index + 1:02d}.png"
        sheet.save(output_path)
        written.append(output_path)

    return written


def main() -> None:
    for path in build_contact_sheets():
        print(path)


if __name__ == "__main__":
    main()
