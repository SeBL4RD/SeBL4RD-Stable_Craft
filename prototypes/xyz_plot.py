"""Compose an A1111-style X/Y/Z plot with Pillow.

The layout follows the original script: X values are columns, Y values are
rows, and each Z value gets its own sub-grid.  Sub-grids are placed side by
side on one page (wrapped into several rows only when the page would become
unreasonably wide).

Every cell image is saved full resolution by the bridge; this module only
builds the labelled contact sheet and its preview.
"""

from __future__ import annotations

import math
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Iterable

from PIL import Image, ImageDraw, ImageFont, ImageOps

LANCZOS = getattr(Image, "Resampling", Image).LANCZOS

# Page width above which Z sub-grids are wrapped instead of a single strip.
MAX_PAGE_WIDTH = 12000


def _font_candidates(bold: bool = False) -> list[str]:
    windir = os.environ.get("WINDIR") or "C:/Windows"
    candidates: list[str] = []
    if os.name == "nt":
        candidates.extend(
            [
                str(Path(windir) / "Fonts" / ("segoeuib.ttf" if bold else "segoeui.ttf")),
                str(Path(windir) / "Fonts" / ("arialbd.ttf" if bold else "arial.ttf")),
            ]
        )
    candidates.extend(
        [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/TTF/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/TTF/DejaVuSans.ttf",
            "/usr/share/fonts/liberation-sans/LiberationSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/liberation-sans/LiberationSans-Regular.ttf",
        ]
    )
    return candidates


def _find_font_path(bold: bool = False) -> str | None:
    for candidate in _font_candidates(bold):
        if Path(candidate).exists():
            return candidate
    # Last chance: ask fontconfig on Linux.
    executable = shutil.which("fc-match")
    if executable:
        try:
            result = subprocess.run(
                [executable, "-f", "%{file}", "sans" if not bold else "sans:bold"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            path = result.stdout.strip()
            if path and Path(path).exists():
                return path
        except Exception:  # noqa: BLE001
            pass
    return None


_FONT_CACHE: dict[tuple[bool, int], Any] = {}


def get_font(size: int, bold: bool = False) -> Any:
    size = max(6, int(size))
    key = (bold, size)
    cached = _FONT_CACHE.get(key)
    if cached is not None:
        return cached
    path = _find_font_path(bold)
    font: Any
    if path:
        try:
            font = ImageFont.truetype(path, size)
        except Exception:  # noqa: BLE001
            font = ImageFont.load_default()
    else:
        font = ImageFont.load_default()
    _FONT_CACHE[key] = font
    return font


def _measure(draw: ImageDraw.ImageDraw, text: str, font: Any) -> tuple[int, int]:
    if not text:
        return 0, 0
    box = draw.textbbox((0, 0), text, font=font)
    return max(0, box[2] - box[0]), max(0, box[3] - box[1])


def wrap_text(
    draw: ImageDraw.ImageDraw, text: str, font: Any, max_width: int
) -> list[str]:
    """Wrap text on spaces, breaking overlong words when necessary."""
    text = " ".join(str(text or "").split())
    if not text or max_width <= 0:
        return []
    lines: list[str] = []
    current = ""
    for word in text.split(" "):
        candidate = f"{current} {word}".strip()
        if _measure(draw, candidate, font)[0] <= max_width or not current:
            if _measure(draw, candidate, font)[0] <= max_width:
                current = candidate
                continue
        if current:
            lines.append(current)
            current = word
        else:
            current = word
        # Break a word that is wider than the available width.
        while _measure(draw, current, font)[0] > max_width and len(current) > 1:
            cut = len(current)
            while cut > 1 and _measure(draw, current[:cut], font)[0] > max_width:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]
    if current:
        lines.append(current)
    return lines


def _draw_multiline(
    draw: ImageDraw.ImageDraw,
    lines: Iterable[str],
    x: int,
    y: int,
    font: Any,
    fill: str,
    *,
    anchor: str = "ma",
    line_gap: int = 2,
) -> int:
    """Draw wrapped lines and return the total height."""
    lines = list(lines)
    if not lines:
        return 0
    line_h = _measure(draw, "Ag", font)[1] + line_gap
    total = line_h * len(lines) - line_gap
    for index, line in enumerate(lines):
        draw.text(
            (x, y + index * line_h),
            line,
            font=font,
            fill=fill,
            anchor=anchor,
        )
    return total


def _cell_image(path: str, max_w: int, max_h: int) -> Image.Image | None:
    try:
        with Image.open(path) as opened:
            image = opened.convert("RGB")
            image.load()
    except Exception:  # noqa: BLE001
        return None
    if image.width > max_w or image.height > max_h:
        image = ImageOps.contain(image, (max_w, max_h), LANCZOS)
    return image


def _placeholder(max_w: int, max_h: int, background: str, border: str) -> Image.Image:
    image = Image.new("RGB", (max(1, max_w), max(1, max_h)), background)
    draw = ImageDraw.Draw(image)
    font = get_font(max(9, min(18, min(max_w, max_h) // 8)))
    draw.text(
        (max_w // 2, max_h // 2),
        "missing",
        font=font,
        fill=border,
        anchor="mm",
    )
    return image


def _sub_grid(
    *,
    cells: dict[tuple[int, int, int], dict[str, Any]],
    x_values: list[str],
    y_values: list[str],
    iz: int,
    z_title: str,
    thumb_w: int,
    thumb_h: int,
    gap: int,
    palette: dict[str, str],
    x_font: Any,
    y_font: Any,
    title_font: Any,
) -> Image.Image:
    cols = max(1, len(x_values))
    rows = max(1, len(y_values))
    calc = Image.new("RGB", (1, 1), palette["background"])
    calc_draw = ImageDraw.Draw(calc)

    # Wrap X and Y labels to the cell width.
    x_lines = [
        wrap_text(calc_draw, value, x_font, max(24, thumb_w - 4))
        for value in (x_values or [""])
    ]
    y_lines = [
        wrap_text(calc_draw, value, y_font, max(24, thumb_w * 3 // 4))
        for value in (y_values or [""])
    ]
    x_line_h = _measure(calc_draw, "Ag", x_font)[1] + 2
    y_line_h = _measure(calc_draw, "Ag", y_font)[1] + 2
    x_block = max((len(lines) for lines in x_lines), default=0) * x_line_h
    y_text_w = max(
        (
            _measure(calc_draw, line, y_font)[0]
            for lines in y_lines
            for line in lines
        ),
        default=0,
    )
    left = (y_text_w + 16) if y_text_w else 0
    title_block = 0
    if z_title:
        title_block = _measure(calc_draw, z_title, title_font)[1] + 10
    top = title_block + (x_block + 12 if x_block else 0)
    grid_w = cols * thumb_w + (cols - 1) * gap
    grid_h = rows * thumb_h + (rows - 1) * gap
    margin = 12
    width = margin + left + grid_w + margin
    height = margin + top + grid_h + margin
    image = Image.new("RGB", (max(1, width), max(1, height)), palette["background"])
    draw = ImageDraw.Draw(image)

    if z_title:
        draw.text(
            (width // 2, margin + 4),
            z_title,
            font=title_font,
            fill=palette["accent"],
            anchor="ma",
        )

    # X labels, centred above each column.
    for ix, lines in enumerate(x_lines):
        x = margin + left + ix * (thumb_w + gap) + thumb_w // 2
        _draw_multiline(
            draw,
            lines,
            x,
            margin + title_block + 2,
            x_font,
            palette["text"],
            anchor="ma",
        )

    # Y labels, right-aligned in the left margin.
    for iy, lines in enumerate(y_lines):
        y = margin + top + iy * (thumb_h + gap) + thumb_h // 2
        total = max(0, len(lines) * y_line_h - 2)
        _draw_multiline(
            draw,
            lines,
            margin + left - 10,
            y - total // 2,
            y_font,
            palette["text"],
            anchor="ra",
        )

    for iy in range(rows):
        for ix in range(cols):
            cell = cells.get((ix, iy, iz))
            path = str(cell.get("path", "")) if cell else ""
            image_cell = _cell_image(path, thumb_w, thumb_h) if path else None
            if image_cell is None:
                image_cell = _placeholder(
                    thumb_w, thumb_h, palette["panel"], palette["muted"]
                )
            cell_x = margin + left + ix * (thumb_w + gap)
            cell_y = margin + top + iy * (thumb_h + gap)
            offset_x = cell_x + (thumb_w - image_cell.width) // 2
            offset_y = cell_y + (thumb_h - image_cell.height) // 2
            image.paste(image_cell, (offset_x, offset_y))
            draw.rectangle(
                (cell_x - 1, cell_y - 1, cell_x + thumb_w, cell_y + thumb_h),
                outline=palette["border"],
                width=1,
            )
    return image


def compose_plot(
    *,
    cells: list[dict[str, Any]],
    x_values: list[str],
    y_values: list[str],
    z_values: list[str],
    title: str,
    axis_lines: list[str],
    legend: list[str] | None,
    out_path: Path,
    preview_path: Path | None = None,
    cell_max: int = 512,
    preview_max: int = 1600,
    dark: bool = True,
    sub_grid_dir: Path | None = None,
) -> dict[str, Any]:
    """Build the labelled plot and its preview.

    ``cells`` items need ``path``, ``ix``, ``iy`` and ``iz`` keys.  The
    remaining values are only used for the labels, which the caller already
    formatted.
    """
    if dark:
        palette = {
            "background": "#1b1b1f",
            "panel": "#25252b",
            "text": "#e8e8ea",
            "muted": "#9a9aa3",
            "accent": "#60a5fa",
            "border": "#3a3a44",
        }
    else:
        palette = {
            "background": "#f4f4f5",
            "panel": "#ffffff",
            "text": "#18181b",
            "muted": "#52525b",
            "accent": "#2563eb",
            "border": "#d4d4d8",
        }

    x_values = list(x_values) or [""]
    y_values = list(y_values) or [""]
    z_values = list(z_values) or [""]
    legend = list(legend or [])

    # Keep one sub-grid manageable.  Individual cells are still saved at full
    # resolution by the bridge; only the contact-sheet thumbnails shrink.
    largest_axis = max(1, len(x_values), len(y_values))
    cell_max = max(64, min(int(cell_max), 8000 // largest_axis))

    # A fixed thumbnail size keeps the grid regular.  The first available
    # image gives the aspect ratio; if none exists, use a square.
    first_image: Image.Image | None = None
    for cell in cells:
        first_image = _cell_image(str(cell.get("path", "")), cell_max, cell_max)
        if first_image is not None:
            break
    if first_image is None:
        thumb_w = thumb_h = max(64, int(cell_max))
    else:
        scale = min(cell_max / max(1, first_image.width), cell_max / max(1, first_image.height))
        thumb_w = max(32, int(round(first_image.width * scale)))
        thumb_h = max(32, int(round(first_image.height * scale)))
    gap = max(4, min(16, thumb_w // 32))
    font_size = max(10, min(28, int(round(min(thumb_w, thumb_h) * 0.045))))
    x_font = get_font(font_size)
    y_font = get_font(font_size)
    title_font = get_font(max(font_size + 2, int(font_size * 1.15)), bold=True)
    header_font = get_font(max(12, int(font_size * 0.8)))
    header_title_font = get_font(max(16, int(font_size * 1.25)), bold=True)

    cell_map: dict[tuple[int, int, int], dict[str, Any]] = {}
    for cell in cells:
        try:
            key = (int(cell.get("ix", 0)), int(cell.get("iy", 0)), int(cell.get("iz", 0)))
        except (TypeError, ValueError):
            continue
        cell_map[key] = cell

    # Build each Z sub-grid.
    sub_grids: list[Image.Image] = []
    for iz, z_value in enumerate(z_values):
        z_title = ""
        if z_value:
            z_title = f"Z: {z_value}"
        sub_grids.append(
            _sub_grid(
                cells=cell_map,
                x_values=x_values,
                y_values=y_values,
                iz=iz,
                z_title=z_title,
                thumb_w=thumb_w,
                thumb_h=thumb_h,
                gap=gap,
                palette=palette,
                x_font=x_font,
                y_font=y_font,
                title_font=title_font,
            )
        )

    sub_grid_paths: list[str] = []
    if sub_grid_dir is not None:
        sub_grid_dir = Path(sub_grid_dir)
        sub_grid_dir.mkdir(parents=True, exist_ok=True)
        for index, grid in enumerate(sub_grids):
            sub_path = sub_grid_dir / f"plot_z{index + 1}.png"
            grid.save(sub_path, "PNG")
            sub_grid_paths.append(str(sub_path))

    margin = 24
    sub_gap = 16

    # A1111 puts the Z sub-grids side by side.  If that would create an
    # unmanageable page, wrap them into several rows.
    widest = max((grid.width for grid in sub_grids), default=1)
    max_cols = max(1, (MAX_PAGE_WIDTH - 2 * margin + sub_gap) // max(1, widest + sub_gap))
    z_cols = min(len(sub_grids), max_cols)
    z_rows = math.ceil(len(sub_grids) / max(1, z_cols)) if sub_grids else 1

    grid_area_w = z_cols * widest + (z_cols - 1) * sub_gap
    page_w = max(640, margin * 2 + grid_area_w)
    calc = Image.new("RGB", (1, 1), palette["background"])
    calc_draw = ImageDraw.Draw(calc)

    # Header: title + axis lines + legend, wrapped to the page width.
    header_lines: list[tuple[str, Any, str]] = []
    if title:
        header_lines.append((title, header_title_font, palette["accent"]))
    for line in axis_lines:
        if line:
            header_lines.append((line, header_font, palette["text"]))
    for line in legend:
        if line:
            header_lines.append((line, header_font, palette["muted"]))
    header_height = margin
    rendered_header: list[tuple[list[str], Any, str, int]] = []
    for text, font, color in header_lines:
        lines = wrap_text(calc_draw, text, font, page_w - margin * 2)
        if not lines:
            continue
        line_h = _measure(calc_draw, "Ag", font)[1] + 2
        rendered_header.append((lines, font, color, line_h))
        header_height += len(lines) * line_h + 3
    header_height += 6

    # Sub-grid rows.
    row_heights: list[int] = []
    for row in range(z_rows):
        start = row * z_cols
        chunk = sub_grids[start : start + z_cols]
        row_heights.append(max((grid.height for grid in chunk), default=1))
    page_h = max(320, header_height + sum(row_heights) + max(0, z_rows - 1) * sub_gap + margin)
    page = Image.new("RGB", (page_w, page_h), palette["background"])
    draw = ImageDraw.Draw(page)

    y = margin
    for lines, font, color, line_h in rendered_header:
        for line in lines:
            draw.text((margin, y), line, font=font, fill=color, anchor="la")
            y += line_h
        y += 3

    y = header_height
    for row in range(z_rows):
        start = row * z_cols
        chunk = sub_grids[start : start + z_cols]
        x = margin
        for grid in chunk:
            page.paste(grid, (x, y))
            x += widest + sub_gap
        y += row_heights[row] + sub_gap

    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    page.save(out_path, "PNG")

    preview_info: dict[str, Any] = {}
    if preview_path is not None:
        preview_path = Path(preview_path)
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview = page.copy()
        factor = max(1, math.ceil(max(preview.width / preview_max, preview.height / preview_max)))
        if factor > 1:
            preview = preview.resize(
                (max(1, preview.width // factor), max(1, preview.height // factor)),
                LANCZOS,
            )
        preview.save(preview_path, "PNG")
        preview_info = {"preview": str(preview_path), "preview_size": preview.size}

    return {
        "path": str(out_path),
        "size": page.size,
        "sub_grids": len(sub_grids),
        "sub_grid_paths": sub_grid_paths,
        "z_cols": z_cols,
        "z_rows": z_rows,
        **preview_info,
    }
