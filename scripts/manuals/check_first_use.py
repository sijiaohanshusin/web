"""Structural first-use gates; every rendered page still needs visual review."""
import json
import hashlib
from pathlib import Path
import re
import shutil

from docx import Document
from docx.oxml.ns import qn
from pypdf import PdfReader
from build_first_use import edition_stem, load_manifest

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs/help/dist'
MANIFEST = json.loads(Path(__file__).with_name('first_use.json').read_text(encoding='utf-8'))
assert re.fullmatch(r'\d{4}-\d{2}-\d{2}', MANIFEST['verified'])
OUT /= MANIFEST['verified']


def release_boundary_errors(status, cover_text, body_text):
    if status == 'candidate':
        return [] if '待上线' in cover_text else ['Candidate manual must state its release boundary']
    errors = []
    for stale in ('尚未上线', '待上线', '网站候选版本'):
        if stale in cover_text + body_text:
            errors.append('Stale publication status: ' + stale)
    # In task steps this wording legitimately describes an author's private draft.
    if '尚未发布' in cover_text:
        errors.append('Stale publication status: 尚未发布')
    return errors


def run(audiences=('recruit', 'member', 'admin')):
    results = []
    for audience in audiences:
        stem = edition_stem(MANIFEST, audience)
        source = OUT / f'{stem}.docx'
        rendered = ROOT / '.shots/documents' / stem
        pdf = rendered / f'{stem}.pdf'
        doc = Document(source)
        errors = []
        if pdf.stat().st_mtime < source.stat().st_mtime:
            errors.append('Stale PDF')
        reader = PdfReader(pdf)
        page_refs = {p.indirect_reference.idnum: i for i, p in enumerate(reader.pages)}
        pdf_targets = []
        for page_number, pdf_page in enumerate(reader.pages):
            targets = []
            for item in pdf_page.get('/Annots', []):
                annotation = item.get_object()
                action = annotation.get('/A')
                action = action.get_object() if action else {}
                if action.get('/S') == '/URI':
                    if not str(action.get('/URI', '')).startswith(('https://heuesta.cn/', 'https://bbs.heuesta.cn/')):
                        errors.append(f'Invalid exported PDF link on page {page_number+1}')
                destination = annotation.get('/Dest') or action.get('/D')
                if destination is not None:
                    destination = destination.get_object()
                    if isinstance(destination, str):
                        named = reader.named_destinations.get(destination)
                        target = reader.get_destination_page_number(named) if named else None
                    else:
                        target = page_refs.get(getattr(destination[0], 'idnum', None))
                    if target is None:
                        errors.append(f'Broken PDF destination on page {page_number+1}')
                    targets.append(target)
            pdf_targets.append(targets)
        planned = MANIFEST[audience]['pages']
        if not set(range(3, len(planned)+3)) <= set(pdf_targets[1]):
            errors.append('PDF contents do not reach every task')
        indexed = {next(i+3 for i, task in enumerate(planned) if task['title'] == title)
                   for _, title in MANIFEST[audience]['index']}
        if not indexed <= set(pdf_targets[2]):
            errors.append('PDF quick index destinations are incomplete')
        feedback_page = next(i+3 for i, p in enumerate(planned) if p['title'] == '提交网站问题与建议')
        for i, targets in enumerate(pdf_targets[1:], 2):
            if not {1, 2, feedback_page} <= set(targets):
                errors.append(f'PDF footer shortcuts missing on page {i}')
        if len(reader.pages) != len(planned) + 3:
            errors.append(f'Expected {len(planned)+3} pages, got {len(reader.pages)}')
        for index, task in enumerate(planned, 4):
            if index > len(reader.pages):
                continue
            text = re.sub(r'\s+', '', reader.pages[index-1].extract_text())
            if task['title'] not in text or '完成检查' not in text or '详细帮助与原图' not in text:
                errors.append(f'Task page {index} incomplete or split')
        names = {node.get(qn('w:name')) for node in doc.element.iter(qn('w:bookmarkStart'))}
        anchors = [node.get(qn('w:anchor')) for node in doc.element.iter(qn('w:hyperlink')) if node.get(qn('w:anchor'))]
        anchors.extend(match[1] for node in doc.element.iter(qn('w:fldSimple'))
                       if (match := re.fullmatch(r'HYPERLINK \\l "([A-Za-z_0-9]+)"', node.get(qn('w:instr'), ''))))
        if not anchors or set(anchors) - names:
            errors.append('Broken internal navigation')
        if not {'contents', 'quick_index', 'feedback_task'} <= names:
            errors.append('Missing task index or feedback shortcut')
        all_text = re.sub(r'\s+', '', '\n'.join(p.extract_text() for p in reader.pages))
        cover_text = re.sub(r'\s+', '', reader.pages[0].extract_text())
        errors.extend(release_boundary_errors(MANIFEST[audience].get('release_status'), cover_text, all_text))
        for required in ('提交网站问题与建议', '跟进反馈与故障求助', '任务速查与操作路线', '1081376858'):
            if required not in all_text:
                errors.append('Missing required guidance: ' + required)
        if '任务速查与操作路线' not in re.sub(r'\s+', '', reader.pages[2].extract_text()):
            errors.append('Quick index is not on page 3')
        for label, title in MANIFEST[audience]['index']:
            n = next(i for i, task in enumerate(planned, 1) if task['title'] == title)
            if f'task_{n}' not in names:
                errors.append('Index destination missing')
        if any(doc.styles.element.iter(qn('w:pBdr'))):
            errors.append('Inherited title border remains')
        if any(not shape._inline.docPr.get('descr') for shape in doc.inline_shapes):
            errors.append('Missing screenshot alternative text')
        if doc.core_properties.author != 'HEU ESTA':
            errors.append('Unexpected metadata author')
        if len(list(rendered.glob('page-*.png'))) != len(reader.pages):
            errors.append('Missing rendered page images')
        for rel in doc.part.rels.values():
            if rel.is_external and not str(rel.target_ref).startswith(('https://heuesta.cn/', 'https://bbs.heuesta.cn/')):
                errors.append('Unexpected external or local link')
        # Copy only an up-to-date structurally complete render for final review.
        if not errors:
            shutil.copy2(pdf, OUT / pdf.name)
        result = {'book':stem,'pages':len(reader.pages),'images':len(doc.inline_shapes),
                  'internal_links':len(anchors),'errors':errors,'visual_review':'required separately',
                  'docx_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
                  'pdf_sha256':hashlib.sha256(pdf.read_bytes()).hexdigest()}
        print(json.dumps(result,ensure_ascii=False))
        results.append(result)
    (ROOT/'.shots/first-use').mkdir(parents=True, exist_ok=True)
    (ROOT/'.shots/first-use/structural-checks.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    if any(item['errors'] for item in results):
        raise SystemExit(1)


if __name__=='__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--audience', choices=['recruit', 'member', 'admin'])
    parser.add_argument('--variant', choices=['honor-ai'])
    args = parser.parse_args()
    MANIFEST = load_manifest(args.variant)
    OUT = ROOT / 'docs/help/dist' / MANIFEST['verified']
    run((args.audience,) if args.audience else ('recruit', 'member', 'admin'))
