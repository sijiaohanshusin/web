from __future__ import annotations

import re
from pathlib import Path

from pypdf import PdfReader


REPO_ROOT = Path(__file__).resolve().parents[2]
MANUALS_DIR = REPO_ROOT / "docs" / "manuals"
DIST_DIR = MANUALS_DIR / "dist"

MANUALS = (
    ("招新注册手册.md", "HEU_ESTA_招新注册手册_2026.pdf", 14),
    ("老会员使用手册.md", "HEU_ESTA_老会员使用手册_2026.pdf", 13),
    ("网站管理手册.md", "HEU_ESTA_网站管理手册_2026.pdf", 16),
)

FORBIDDEN_TEXT = (
    (
        re.compile(
            r"(?i)\b(?:server|origin|ssh|服务器|源站).{0,24}(?:ip|address|地址)"
            r"\s*[:：=]\s*\d{1,3}(?:\.\d{1,3}){3}\b"
        ),
        "server address",
    ),
    (
        re.compile(
            r"(?i)\b(?:password|passwd|client_secret|refresh_token|密码|密钥)\b"
            r"\s*[:：=]\s*[\"']?[^\s\"']{8,}"
        ),
        "literal credential",
    ),
    (re.compile(r"GOCSPX-[A-Za-z0-9_-]+"), "Google OAuth client secret"),
    (re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"), "private key"),
)


def validate_markdown(source_path: Path, expected_chapters: int) -> list[str]:
    errors: list[str] = []
    source = source_path.read_text(encoding="utf-8")
    chapters = re.findall(r"^##\s+\d+\.\s+", source, flags=re.MULTILINE)
    if len(chapters) != expected_chapters:
        errors.append(
            f"{source_path.name}: expected {expected_chapters} numbered chapters, found {len(chapters)}"
        )

    for alt, relative_path in re.findall(r"!\[([^\]]*)\]\(([^)]+)\)", source):
        image_path = (source_path.parent / relative_path).resolve()
        if not image_path.is_file():
            errors.append(f"{source_path.name}: missing image {relative_path!r} ({alt})")

    for pattern, label in FORBIDDEN_TEXT:
        if pattern.search(source):
            errors.append(f"{source_path.name}: contains forbidden {label}")
    return errors


def validate_pdf(pdf_path: Path, title: str) -> tuple[list[str], int]:
    errors: list[str] = []
    if not pdf_path.is_file():
        return [f"missing PDF: {pdf_path.name}"], 0

    reader = PdfReader(str(pdf_path))
    page_count = len(reader.pages)
    if page_count < 10:
        errors.append(f"{pdf_path.name}: unexpectedly short ({page_count} pages)")

    extracted = "\n".join((page.extract_text() or "") for page in reader.pages)
    if title not in extracted:
        errors.append(f"{pdf_path.name}: title is not extractable")
    if "# HEU ESTA" in extracted:
        errors.append(f"{pdf_path.name}: raw Markdown H1 marker remains")
    for pattern, label in FORBIDDEN_TEXT:
        if pattern.search(extracted):
            errors.append(f"{pdf_path.name}: contains forbidden {label}")
    return errors, page_count


def main() -> None:
    errors: list[str] = []
    summary: list[str] = []
    for markdown_name, pdf_name, chapters in MANUALS:
        markdown_path = MANUALS_DIR / markdown_name
        errors.extend(validate_markdown(markdown_path, chapters))
        pdf_errors, pages = validate_pdf(DIST_DIR / pdf_name, markdown_path.stem)
        errors.extend(pdf_errors)
        summary.append(f"{markdown_name}: {chapters} chapters, {pages} PDF pages")

    if errors:
        for error in errors:
            print(f"ERROR: {error}")
        raise SystemExit(1)

    for line in summary:
        print(f"OK: {line}")
    print("OK: screenshot references, PDF text, page counts, and forbidden-text scan passed")


if __name__ == "__main__":
    main()
