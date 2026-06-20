"""Generate DeyeCloud brand PNG assets for Home Assistant from root brand/ SVGs."""

from __future__ import annotations

from io import BytesIO
from pathlib import Path

try:
    from PIL import Image
except ImportError:
    raise SystemExit("Pillow is required: pip install pillow") from None

ROOT = Path(__file__).resolve().parents[1]
SOURCE_DIR = ROOT / "brand"
BRAND_DIR = ROOT / "custom_components" / "deyecloud" / "brand"

ICON_SVG = SOURCE_DIR / "icon.svg"
LOGO_SVG = SOURCE_DIR / "logo.svg"

ICON_SIZES = {
    "icon.png": (128, 128),
    "icon@2x.png": (256, 256),
}
LOGO_SIZES = {
    "logo.png": (320, 128),
    "logo@2x.png": (640, 256),
}


def _fit_in_box(image: Image.Image, width: int, height: int) -> Image.Image:
    """Scale image to fit inside width x height, centered on transparent canvas."""
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    src_width, src_height = image.size
    scale = min(width / src_width, height / src_height)
    new_width = max(1, int(src_width * scale))
    new_height = max(1, int(src_height * scale))
    resized = image.resize((new_width, new_height), Image.Resampling.LANCZOS)
    offset_x = (width - new_width) // 2
    offset_y = (height - new_height) // 2
    canvas.paste(resized, (offset_x, offset_y), resized)
    return canvas


def _rasterize_svg(svg_path: Path, width: int, height: int) -> Image.Image:
    try:
        import cairosvg
    except ImportError as exc:
        raise SystemExit("cairosvg is required: pip install cairosvg") from exc

    png_data = cairosvg.svg2png(
        url=str(svg_path),
        output_width=width * 2,
        output_height=height * 2,
    )
    image = Image.open(BytesIO(png_data)).convert("RGBA")
    return image.resize((width, height), Image.Resampling.LANCZOS)


def _resolve_icon_source() -> tuple[Image.Image, Path]:
    if not ICON_SVG.exists():
        raise SystemExit(f"Missing required icon source: {ICON_SVG}")
    print(f"Using icon source: {ICON_SVG}")
    return _rasterize_svg(ICON_SVG, 256, 256), ICON_SVG


def _resolve_logo_source() -> tuple[Image.Image, Path]:
    logo_path = LOGO_SVG if LOGO_SVG.exists() else ICON_SVG
    if not logo_path.exists():
        raise SystemExit(f"Missing logo source: {LOGO_SVG} (and fallback {ICON_SVG})")
    if logo_path is ICON_SVG and not LOGO_SVG.exists():
        print(f"logo.svg not found, using icon.svg for logo: {ICON_SVG}")
    else:
        print(f"Using logo source: {logo_path}")
    return _rasterize_svg(logo_path, 640, 256), logo_path


def main() -> None:
    BRAND_DIR.mkdir(parents=True, exist_ok=True)

    icon_source, icon_path = _resolve_icon_source()
    logo_source, logo_path = _resolve_logo_source()

    outputs: dict[str, Image.Image] = {}
    for name, size in ICON_SIZES.items():
        outputs[name] = _fit_in_box(icon_source, *size)
    for name, size in LOGO_SIZES.items():
        outputs[name] = _fit_in_box(logo_source, *size)

    for name, image in outputs.items():
        image.save(BRAND_DIR / name, format="PNG")
        print(f"Wrote {BRAND_DIR / name}")

    print(f"Icon from {icon_path.name}; logo from {logo_path.name}")


if __name__ == "__main__":
    main()
