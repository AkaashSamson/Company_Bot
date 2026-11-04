"""Unit tests for image_normalizer utility."""

from io import BytesIO
from PIL import Image

from app.infrastructure.document.image_normalizer import (
    guard_max_dimension,
    is_blank_page,
    normalize_alpha_to_white,
)


def test_normalize_alpha_to_white_with_rgba():
    # Create an RGBA image with transparent background and red square
    img = Image.new("RGBA", (100, 100), (0, 0, 0, 0))
    for x in range(20, 80):
        for y in range(20, 80):
            img.putpixel((x, y), (255, 0, 0, 255))

    buf = BytesIO()
    img.save(buf, format="PNG")
    raw_bytes = buf.getvalue()

    out_bytes, out_img = normalize_alpha_to_white(raw_bytes)
    assert out_img.mode == "RGB"
    assert out_img.size == (100, 100)

    # Check that corner pixel (which was transparent) is now pure white (255, 255, 255)
    corner_pixel = out_img.getpixel((0, 0))
    assert corner_pixel == (255, 255, 255)

    # Check that center pixel is still red (255, 0, 0)
    center_pixel = out_img.getpixel((50, 50))
    assert center_pixel == (255, 0, 0)


def test_normalize_alpha_to_white_with_already_rgb():
    img = Image.new("RGB", (50, 50), (120, 120, 120))
    buf = BytesIO()
    img.save(buf, format="PNG")

    out_bytes, out_img = normalize_alpha_to_white(buf.getvalue())
    assert out_img.mode == "RGB"
    assert out_img.getpixel((25, 25)) == (120, 120, 120)


def test_guard_max_dimension_resizes_large_image():
    # Image larger than 1024 (e.g. 2000 x 1000)
    img = Image.new("RGB", (2000, 1000), (50, 50, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")

    out_bytes, out_img = guard_max_dimension(buf.getvalue(), max_dim=1024)
    assert out_img.size == (1024, 512)
    assert max(out_img.size) == 1024


def test_guard_max_dimension_keeps_small_image():
    img = Image.new("RGB", (400, 300), (50, 50, 50))
    buf = BytesIO()
    img.save(buf, format="PNG")

    out_bytes, out_img = guard_max_dimension(buf.getvalue(), max_dim=1024)
    assert out_img.size == (400, 300)


def test_is_blank_page_detects_pure_white():
    img = Image.new("RGB", (800, 1000), (255, 255, 255))
    assert is_blank_page(img) is True


def test_is_blank_page_detects_dusty_white():
    # Pure white with 10 stray dust pixels
    img = Image.new("RGB", (800, 1000), (250, 250, 250))
    for i in range(10):
        img.putpixel((i, i), (50, 50, 50))
    assert is_blank_page(img) is True


def test_is_blank_page_detects_content():
    img = Image.new("RGB", (800, 1000), (255, 255, 255))
    # Draw significant black lines / content
    for x in range(100, 300):
        for y in range(100, 150):
            img.putpixel((x, y), (0, 0, 0))
    assert is_blank_page(img) is False
