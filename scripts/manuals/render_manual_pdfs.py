from __future__ import annotations

import argparse
from pathlib import Path

import pypdfium2 as pdfium


def render_pdf(pdf_path: Path, output_dir: Path, scale: float) -> int:
    output_dir.mkdir(parents=True, exist_ok=True)
    for old_page in output_dir.glob("page-*.png"):
        old_page.unlink()

    document = pdfium.PdfDocument(str(pdf_path))
    page_count = len(document)
    for index in range(page_count):
        page = document[index]
        bitmap = page.render(scale=scale)
        image = bitmap.to_pil()
        image.save(output_dir / f"page-{index + 1:03d}.png", optimize=True)
        page.close()
    document.close()
    return page_count


def main() -> None:
    parser = argparse.ArgumentParser(description="Render exported manual PDFs to page PNGs.")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("output_dir", type=Path)
    parser.add_argument("--scale", type=float, default=2.0)
    args = parser.parse_args()

    pages = render_pdf(args.pdf.resolve(), args.output_dir.resolve(), args.scale)
    print(f"Rendered {pages} pages from {args.pdf}")


if __name__ == "__main__":
    main()
