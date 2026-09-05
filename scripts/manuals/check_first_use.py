"""Structural first-use gates; every rendered page still needs visual review."""
import json
from pathlib import Path
import re
import shutil

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/help/dist'
MANIFEST = json.loads(Path(__file__).with_name('first_use.json').read_text(encoding='utf-8'))


def run():
    results = []
    for audience in ('recruit', 'member', 'admin'):
        stem = audience + '-first-use'
        source = OUT / f'{stem}.docx'
        rendered = ROOT / '.shots/documents' / stem
        pdf = rendered / f'{stem}.pdf'
        doc = Document(source)
        errors = []
        if pdf.stat().st_mtime < source.stat().st_mtime:
            errors.append('Stale PDF')
        reader = PdfReader(pdf)
        planned = MANIFEST[audience]['pages']
        if len(reader.pages) != len(planned) + 2:
            errors.append(f'Expected {len(planned)+2} pages, got {len(reader.pages)}')
        for index, task in enumerate(planned, 3):
            if index > len(reader.pages):
                continue
            text = re.sub(r'\s+', '', reader.pages[index-1].extract_text())
            if task['title'] not in text or '完成检查' not in text or '详细帮助与原图' not in text:
                errors.append(f'Task page {index} incomplete or split')
        names = {node.get(qn('w:name')) for node in doc.element.iter(qn('w:bookmarkStart'))}
        anchors = [node.get(qn('w:anchor')) for node in doc.element.iter(qn('w:hyperlink')) if node.get(qn('w:anchor'))]
        if not anchors or set(anchors) - names:
            errors.append('Broken internal navigation')
        if any(doc.styles.element.iter(qn('w:pBdr'))):
            errors.append('Inherited title border remains')
        if any(not shape._inline.docPr.get('descr') for shape in doc.inline_shapes):
            errors.append('Missing screenshot alternative text')
        if doc.core_properties.author != 'HEU ESTA':
            errors.append('Unexpected metadata author')
        if len(list(rendered.glob('page-*.png'))) != len(reader.pages):
            errors.append('Missing rendered page images')
        for rel in doc.part.rels.values():
            if rel.is_external and not str(rel.target_ref).startswith('https://heuesta.cn/'):
                errors.append('Unexpected external or local link')
        # Copy only an up-to-date structurally complete render for final review.
        if not errors:
            shutil.copy2(pdf, OUT / pdf.name)
        result = {'book':stem,'pages':len(reader.pages),'images':len(doc.inline_shapes),
                  'internal_links':len(anchors),'errors':errors,'visual_review':'required separately'}
        print(json.dumps(result,ensure_ascii=False))
        results.append(result)
    (ROOT/'.shots/first-use/structural-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(item['errors'] for item in results):
        raise SystemExit(1)


if __name__=='__main__':
    run()
