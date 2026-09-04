from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


def main() -> None:
    parser = argparse.ArgumentParser(description="Build QA contact sheets from rendered manual pages.")
    parser.add_argument("pages_dir", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--columns", type=int, default=3)
    parser.add_argument("--rows", type=int, default=2)
    parser.add_argument("--page-width", type=int, default=360)
    args = parser.parse_args()

    pages = sorted(args.pages_dir.glob("page-*.png"))
    args.output_dir.mkdir(parents=True, exist_ok=True)
    for old_sheet in args.output_dir.glob("sheet-*.jpg"):
        old_sheet.unlink()

    per_sheet = args.columns * args.rows
    gap = 24
    label_height = 34
    page_height = round(args.page_width * 1.4142)
    sheet_width = args.columns * args.page_width + (args.columns + 1) * gap
    sheet_height = args.rows * (page_height + label_height) + (args.rows + 1) * gap
    font = ImageFont.load_default(size=18)

    for sheet_index in range(math.ceil(len(pages) / per_sheet)):
        sheet = Image.new("RGB", (sheet_width, sheet_height), "#dfe6ea")
        draw = ImageDraw.Draw(sheet)
        batch = pages[sheet_index * per_sheet : (sheet_index + 1) * per_sheet]
        for slot, page_path in enumerate(batch):
            row, column = divmod(slot, args.columns)
            x = gap + column * (args.page_width + gap)
            y = gap + row * (page_height + label_height + gap)
            with Image.open(page_path) as page:
                page = page.convert("RGB")
                page.thumbnail((args.page_width, page_height), Image.Resampling.LANCZOS)
                sheet.paste(page, (x, y))
            draw.text((x, y + page_height + 5), page_path.stem, fill="#17212b", font=font)
        target = args.output_dir / f"sheet-{sheet_index + 1:02d}.jpg"
        sheet.save(target, quality=90, optimize=True)

    print(f"Built {math.ceil(len(pages) / per_sheet)} contact sheets from {len(pages)} pages")


if __name__ == "__main__":
    main()
