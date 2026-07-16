from __future__ import annotations

from PIL import Image, ImageDraw
import pytest

from src.slides.selection_geometry import (
    SelectionRectImg,
    image_point_to_pdf_point,
    image_rect_to_pdf_rect,
    snap_to_ink,
    view_point_to_image_point,
)


def test_image_point_to_pdf_point_top_left_maps_to_crop_top_left() -> None:
    # Arrange
    img_w = 200
    img_h = 100
    crop_w = 200
    crop_h = 100
    crop_x0 = 10
    crop_y0 = 20

    # Act
    x_pt, y_pt = image_point_to_pdf_point(
        0,
        0,
        img_w=img_w,
        img_h=img_h,
        crop_w=crop_w,
        crop_h=crop_h,
        crop_x0=crop_x0,
        crop_y0=crop_y0,
    )

    # Assert
    assert x_pt == pytest.approx(crop_x0)
    assert y_pt == pytest.approx(crop_y0 + crop_h)


@pytest.mark.parametrize(
    ("rotation", "expected"),
    [
        (0, (0, 0, 100, 50)),
        (90, (0, 0, 50, 100)),
        (180, (0, 0, 100, 50)),
        (270, (0, 0, 50, 100)),
    ],
)
def test_image_rect_to_pdf_rect_rotation_full_page(rotation: int, expected: tuple[int, int, int, int]) -> None:
    # Arrange
    rect = SelectionRectImg(x=0, y=0, w=100, h=50)

    # Act
    pdf_rect = image_rect_to_pdf_rect(
        rect,
        img_w=100,
        img_h=50,
        crop_w=100,
        crop_h=50,
        crop_x0=0,
        crop_y0=0,
        rotation=rotation,
    )

    # Assert
    assert pdf_rect.x == pytest.approx(expected[0])
    assert pdf_rect.y == pytest.approx(expected[1])
    assert pdf_rect.w == pytest.approx(expected[2])
    assert pdf_rect.h == pytest.approx(expected[3])


def test_view_point_to_image_point_zoom_pan() -> None:
    # Arrange
    x_view = 110
    y_view = 220

    # Act
    x_img, y_img = view_point_to_image_point(
        x_view,
        y_view,
        zoom=2.0,
        pan_x=10,
        pan_y=20,
        img_w=500,
        img_h=400,
    )

    # Assert
    assert x_img == pytest.approx(50)
    assert y_img == pytest.approx(100)


def test_image_rect_to_pdf_rect_rotation_with_crop_offset() -> None:
    # Arrange
    rect = SelectionRectImg(x=10, y=5, w=20, h=10)

    # Act
    pdf_rect = image_rect_to_pdf_rect(
        rect,
        img_w=100,
        img_h=50,
        crop_w=200,
        crop_h=100,
        crop_x0=10,
        crop_y0=20,
        rotation=90,
    )

    # Assert
    assert pdf_rect.x == pytest.approx(20)
    assert pdf_rect.y == pytest.approx(40)
    assert pdf_rect.w == pytest.approx(20)
    assert pdf_rect.h == pytest.approx(40)


def test_snap_to_ink_tightens_bbox_for_black_text() -> None:
    # Arrange
    image = Image.new("RGB", (100, 50), "white")
    draw = ImageDraw.Draw(image)
    draw.rectangle((30, 15, 70, 30), fill="black")
    rect = SelectionRectImg(x=10, y=5, w=80, h=40)

    # Act
    tightened = snap_to_ink(image, rect)

    # Assert
    assert tightened.x <= 30
    assert tightened.y <= 15
    assert tightened.x + tightened.w >= 70
    assert tightened.y + tightened.h >= 30
    assert tightened.w < rect.w
    assert tightened.h < rect.h
