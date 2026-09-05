"""Structural gates and screenshot readability warnings, not visual approval."""
import json
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.oxml.ns import qn
from PIL import Image
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / '.shots' / 'documents'
BOOKS = ('recruit', 'member', 'admin')


def run():
    results = []
    for book in BOOKS:
        source = ROOT / 'docs/help/dist' / f'{book}.docx'
        doc = Document(source)
        names = {item.get(qn('w:name')) for item in doc.element.iter(qn('w:bookmarkStart'))}
        anchors = [item.get(qn('w:anchor')) for item in doc.element.iter(qn('w:hyperlink'))
                   if item.get(qn('w:anchor'))]
        problems, warnings = [], []
        if not anchors or any(anchor not in names for anchor in anchors):
            problems.append('Missing or broken internal task links')
        if doc.settings.element.find(qn('w:updateFields')) is None:
            problems.append('Page fields do not update on open')
        if doc.core_properties.author != 'HEU ESTA':
            problems.append('Unexpected author metadata')
        pdf_path = OUT / book / f'{book}.pdf'
        page_count = 0
        if not pdf_path.exists() or pdf_path.stat().st_mtime < source.stat().st_mtime:
            problems.append('PDF render is missing or older than DOCX')
        else:
            reader = PdfReader(pdf_path)
            page_count = len(reader.pages)
            for number, page in enumerate(reader.pages, 1):
                body = ''.join(page.extract_text().splitlines()[2:]).strip()
                if body == '返回任务目录':
                    problems.append(f'Page {number} contains only a return link')
        images = []
        for shape in doc.inline_shapes:
            blip = shape._inline.graphic.graphicData.pic.blipFill.blip
            part = doc.part.related_parts[blip.embed]
            with Image.open(BytesIO(part.blob)) as image:
                width, height = image.size
            label = shape._inline.docPr.get('descr') or ''
            if not label:
                problems.append('Screenshot without alternative text')
            displayed_inches = shape.width / 914400
            ppi = width / displayed_inches
            images.append({'label': label, 'pixels': [width, height], 'effective_ppi': round(ppi)})
            # Assuming 14px UI copy, over 140 PPI puts it below 7.2pt on paper.
            # Screenshots vary: this is a crop-review queue, not a pass/fail score.
            if ppi > 140:
                warnings.append({'label': label, 'effective_ppi': round(ppi),
                                 'action': 'Inspect at 100%; replace full page with a focused crop where needed'})
        results.append({'book': book, 'pdf_pages': page_count, 'internal_links': len(anchors), 'images': images,
                        'problems': problems, 'readability_warnings': warnings,
                        'visual_review': 'not certified by this script'})
        print(f'{book}: {page_count} PDF pages, {len(anchors)} internal links, {len(images)} images, '
              f'{len(problems)} structural errors, {len(warnings)} crop-review warnings')
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'checks.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    if any(item['problems'] for item in results):
        raise SystemExit(1)


if __name__ == '__main__':
    run()
