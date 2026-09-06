"""Curated first-use editions; instructions remain in helpcenter Markdown."""
import argparse
from io import BytesIO
import json
import os
from pathlib import Path
import re
import subprocess

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Mm, Pt, RGBColor
from PIL import Image, ImageDraw, ImageFont

from build_help import ASSETS, CONTENT, ROOT, OUT, bookmark, field, inline, link

MANIFEST = Path(__file__).with_name('first_use.json')
QA = ROOT / '.shots/first-use'
AUDIENCES = ('recruit', 'member', 'admin')


def edition_stem(config, audience):
    suffix = '-' + config['output_suffix'] if config.get('output_suffix') else ('-works-wall-preview' if config[audience].get('release_status') == 'candidate' else '')
    return audience + '-first-use' + suffix


# Coordinates refer to the original sanitized screenshots, never fabricated UI.
CROPS = {
    'shared-01-register-channel-choice.png': (85, 280, 1345, 810),
    'recruitment-02-register-step-identity.png': (505, 230, 1230, 760),
    'recruitment-03-register-step-contact.png': (505, 300, 1230, 785),
    'recruitment-08-application-step-interests.png': (960, 410, 1335, 940),
    'recruitment-11-application-step-confirm.png': (960, 615, 1335, 1000),
    'first-use-application-mobile.png': (0, 0, 302, 224),
    'recruitment-12-application-status-submitted.png': (945, 570, 1340, 995),
    'recruitment-07-application-step-direction.png': (100, 742, 825, 925),
    'returning-member-02-register-step-identity.png': (500, 215, 1230, 845),
    'returning-member-03-register-step-contact.png': (505, 300, 1230, 795),
    'shared-02-password-login.png': (505, 330, 1110, 785),
    'workspace-start.png': (275, 212, 930, 566),
    'workspace-card.png': (275, 280, 945, 580),
    'workspace-publish.png': (977, 385, 1425, 678),
    'admin-01-dashboard-overview.png': (0, 0, 232, 465),
    'admin-02-member-search.png': (258, 90, 1100, 560),
    'admin-03-returning-review.png': (1085, 220, 1407, 440),
    'admin-07-application-detail.png': (860, 145, 1410, 530),
    'forum-first-topic-desktop.png': (0, 0, 1331, 220),
    'forum-first-reply.png': (0, 0, 1331, 220),
    'forum-first-topic-mobile.png': (0, 0, 390, 184),
    'forum-queue-review.png': (0, 0, 810, 565),
    'manual-works-wall.png': (300, 430, 962, 639),
}


def article(ref):
    if not re.fullmatch(r'(recruit|member|admin)/[a-z-]+', ref):
        raise ValueError(f'Invalid article reference: {ref}')
    _, header, body = (CONTENT / f'{ref}.md').read_text(encoding='utf-8').split('---', 2)
    meta = json.loads(header)
    sections = {}
    heading = ''
    for line in body.splitlines():
        if line.startswith('## '):
            heading = line[3:].strip()
            sections[heading] = []
        elif line.strip() and not line.startswith('![') and not re.match(r'^\*[^*]', line):
            sections.setdefault(heading, []).append(line.strip())
    return meta, sections


def excerpt(ref, section, items=None):
    _, sections = article(ref)
    lines = sections[section]
    if items is not None:
        numbered = {int(m[1]): m[2] for line in lines
                    if (m := re.match(r'^(\d+)\. (.*)', line))}
        return [numbered[index] for index in items]
    return [re.sub(r'^\d+\. ', '', line) for line in lines]


def picture(name):
    with Image.open(ASSETS / name) as source:
        result = source.convert('RGB')
        if name in CROPS:
            box = CROPS[name]
            if not (0 <= box[0] < box[2] <= result.width and 0 <= box[1] < box[3] <= result.height):
                raise ValueError(f'Crop outside source: {name}')
            result = result.crop(box)
        return result


def inventory(config):
    names = list(dict.fromkeys(p[k] for book in AUDIENCES for p in config[book]['pages']
                              for k in ('image', 'image2') if k in p))
    font = ImageFont.truetype('C:/Windows/Fonts/arial.ttf', 13)
    QA.mkdir(parents=True, exist_ok=True)
    for group in range(0, len(names), 9):
        sheet = Image.new('RGB', (1050, 1140), '#eeeeee')
        draw = ImageDraw.Draw(sheet)
        for index, name in enumerate(names[group:group+9]):
            image = picture(name)
            label = f'{group+index+1}. {name}\n{image.width} x {image.height}'
            image.thumbnail((340, 327))
            x, y = index % 3 * 350, index // 3 * 380
            draw.text((x+5, y+5), label, font=font, fill='black')
            sheet.paste(image, (x+5, y+48))
        sheet.save(QA / f'inventory-{group//9+1}.png')


def configure(doc, title, audience):
    sec = doc.sections[0]
    sec.page_width, sec.page_height = Mm(210), Mm(297)
    sec.top_margin, sec.bottom_margin = Mm(17), Mm(17)
    sec.left_margin = sec.right_margin = Mm(19)
    sec.header_distance = sec.footer_distance = Mm(8)
    sec.different_first_page_header_footer = True
    # Word's default template may supply a blue Title border and theme fonts.
    # Remove inherited decoration before applying our explicit typography.
    for element in list(doc.styles.element.iter(qn('w:pBdr'))):
        element.getparent().remove(element)
    for name in ('Normal', 'Title', 'Subtitle', 'Heading 1', 'Heading 2', 'Heading 3', 'Caption'):
        style = doc.styles[name]
        style.font.name = 'Microsoft YaHei'
        style._element.get_or_add_rPr().rFonts.set(qn('w:eastAsia'), 'Microsoft YaHei')
        fonts = style._element.get_or_add_rPr().rFonts
        for attr in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
            fonts.attrib.pop(qn('w:' + attr), None)
        style.font.color.rgb = RGBColor(0, 0, 0)
        style.font.italic = False
        style.font.bold = name.startswith('Heading') or name == 'Title'
    normal = doc.styles['Normal']
    normal.font.size = Pt(11)
    normal.paragraph_format.line_spacing = 1.15
    normal.paragraph_format.space_after = Pt(5)
    snap = OxmlElement('w:snapToGrid'); snap.set(qn('w:val'), '0')
    normal._element.get_or_add_pPr().append(snap)
    for name, size in [('Title', 29), ('Heading 1', 22), ('Heading 2', 12), ('Subtitle', 11)]:
        style = doc.styles[name]
        style.font.size = Pt(size)
        style.paragraph_format.space_before = Pt(8)
        style.paragraph_format.space_after = Pt(6)
        style.paragraph_format.keep_with_next = True
    doc.styles['Caption'].font.size = Pt(8.5)
    doc.styles['Caption'].font.color.rgb = RGBColor.from_string('48515B')
    doc.styles['Caption'].paragraph_format.space_after = Pt(5)
    sec.header.paragraphs[0].text = 'HEU ESTA    ' + title + ('    内部使用' if audience == 'admin' else '')
    sec.header.paragraphs[0].style = 'Caption'
    sec.header.paragraphs[0].runs[0].font.color.rgb = RGBColor(0, 0, 0)
    p = sec.footer.paragraphs[0]
    p.style = 'Caption'
    p.add_run('首次上手  |  2026.09  |  ')
    field(p, 'PAGE'); p.add_run(' / '); field(p, 'NUMPAGES')
    p.add_run('    '); link(p, '返回目录', '#contents')
    p.add_run('  |  '); link(p, '任务速查', '#quick_index')
    p.add_run('  |  '); link(p, '遇到 BUG', '#feedback_task')
    update = OxmlElement('w:updateFields'); update.set(qn('w:val'), 'true')
    doc.settings.element.append(update)
    doc.core_properties.title = title
    doc.core_properties.author = 'HEU ESTA'
    doc.core_properties.subject = '网站首次使用与任务导航'


def add_lines(doc, lines, numbered=True):
    for index, text in enumerate(lines, 1):
        p = doc.add_paragraph()
        if numbered:
            p.paragraph_format.left_indent = Mm(6)
            p.paragraph_format.first_line_indent = Mm(-6)
            p.add_run(f'{index}. ').bold = True
        inline(p, text.removeprefix('- '))


def add_picture(doc, name, label, max_height=85):
    img = picture(name)
    # Show narrow phone captures at a natural readable width, not desktop width.
    width = min(172, 92 if img.width < 600 else 172, max_height * img.width / img.height)
    stream = BytesIO(); img.save(stream, format='PNG'); stream.seek(0)
    p = doc.add_paragraph()
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p.paragraph_format.space_before = Pt(4)
    p.paragraph_format.space_after = Pt(2)
    p.paragraph_format.keep_with_next = True
    shape = p.add_run().add_picture(stream, width=Mm(width))
    shape._inline.docPr.set('descr', label)
    doc.add_paragraph(label, 'Caption')
    return {'name': name, 'pixels': list(img.size), 'width_mm': round(width, 1),
            'ppi': round(img.width / (width / 25.4)), 'crop': CROPS.get(name)}


def make_book(config, audience, revision):
    book = config[audience]
    doc = Document(); configure(doc, book['title'], audience)
    evidence = []
    markdown = [f"# {book['title']}", '', book['intro'], '',
                f"核验日期 {config['verified']} · 基础版本 {config['site_version']}", '',
                '## 任务目录', '']
    task_numbers = {page['title']: n for n, page in enumerate(book['pages'], 1)}
    for title, n in task_numbers.items():
        markdown.append(f'- [{n:02d} {title}](#task-{n})')
    markdown.extend(['', '## 任务速查', '', book['journey'], ''])
    for label, title in book['index']:
        markdown.append(f'- {label}：[任务 {task_numbers[title]:02d} {title}](#task-{task_numbers[title]})')
    doc.add_paragraph('哈尔滨工程大学电子科技协会', 'Subtitle')
    p = doc.add_paragraph('FIRST USE  /  ' + {'recruit':'01 RECRUIT','member':'02 MEMBER','admin':'03 ADMIN'}[audience])
    p.paragraph_format.space_before = Pt(30)
    p.paragraph_format.space_after = Pt(16)
    p.runs[0].font.color.rgb = RGBColor.from_string('126472')
    doc.add_paragraph(book['title'], 'Title')
    doc.add_paragraph(config['edition'], 'Subtitle')
    doc.add_paragraph(book['intro'])
    doc.add_heading('从哪里开始', 2)
    starts = {
        'recruit': [('还没有账号', 1), ('已经注册但未报名', 5), ('已经提交报名', 9)],
        'member': [('需要恢复老会员身份', 1), ('已经审核通过', 3), ('只想学习发帖', 6), ('只想设计公开卡片', 8)],
        'admin': [('第一次接手管理', 1), ('正在处理成员申请', 3), ('需要发布公告', 6), ('已有论坛审核权限', 9)],
    }
    for label, task in starts[audience]:
        p = doc.add_paragraph(); link(p, f'{label}  从任务 {task:02d} 开始', f'#task_{task}')
    if audience == 'member':
        task = task_numbers['上传作品到协会作品墙']
        p = doc.add_paragraph(); link(p, f'只想上传到协会作品墙  从任务 {task:02d} 开始', f'#task_{task}')
    doc.add_heading('怎样使用这本手册', 2)
    doc.add_paragraph('第一次使用可顺序阅读；已有账号直接查第 3 页“任务速查”。每页按“入口 → 步骤 → 对照截图 → 完成检查”操作。目录和页脚可点击跳转；打印后按页码查找，PDF 也可搜索“作品”“验证码”等关键词。')
    p = doc.add_paragraph(); link(p, '遇到 BUG 或想提建议，直接看反馈章节', '#feedback_task')
    doc.add_heading('适用版本', 2)
    release_note = book.get('release_note') or f'核验日期 {config["verified"]}。对应已上线的网站版本 {config["site_version"]}，不是开发模式。保留仍适用的 9 月 4–5 日截图，并补充 9 月 6 日作品与反馈截图；具体图源日期见每页。'
    doc.add_paragraph(release_note)
    markdown.extend(['## 适用版本', '', release_note, ''])
    doc.add_paragraph('新操作图来自同版隔离环境中的虚构成员；公开反馈表单在正式站只读核对，未提交演示记录。示例身份与内容不用于正式业务。网站后续改版时，以当前界面和网页帮助为准。', 'Caption')
    p = doc.add_paragraph(); link(p, '打开本册网页帮助', f'https://heuesta.cn/help/{audience}/')
    doc.add_page_break()
    bookmark(doc.add_heading('首次任务目录', 1), 'contents')
    doc.add_paragraph('点击任务名称跳转。也可以打印后逐项完成。')
    for n, page in enumerate(book['pages'], 1):
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(1 if len(book['pages']) > 22 else 3)
        p.paragraph_format.space_after = Pt(3 if len(book['pages']) > 22 else 5)
        p.add_run(f'{n:02d}   ').bold = True
        link(p, page['title'], f'#task_{n}')
        p.add_run('    '); field(p, f'PAGEREF task_{n} \\h')
    doc.add_heading('需要更详细的操作', 2)
    doc.add_paragraph('每个任务末尾有详细帮助链接；权限、批量管理和系统配置按网页章节查阅。个人展示作品和全站项目不是同一入口，普通会员不要照搬管理员操作。')
    heading = doc.add_heading('任务速查与操作路线', 1)
    heading.paragraph_format.page_break_before = True
    bookmark(heading, 'quick_index')
    doc.add_paragraph(book['journey'])
    doc.add_paragraph('按你现在要做的事查找，不必从头翻。右栏可点击，页码供纸本使用。')
    table = doc.add_table(rows=1, cols=2)
    table.autofit = False
    table.columns[0].width = Mm(80); table.columns[1].width = Mm(92)
    for cell, label in zip(table.rows[0].cells, ('我想做什么或遇到什么', '去哪个任务')):
        cell.text = label
    for label, title in book['index']:
        cells = table.add_row().cells
        cells[0].text = label
        n = task_numbers[title]
        p = cells[1].paragraphs[0]
        link(p, f'{n:02d} {title}', f'#task_{n}')
        p.add_run('  · 第 '); field(p, f'PAGEREF task_{n} \\h'); p.add_run(' 页')
    for i, row in enumerate(table.rows):
        for cell in row.cells:
            props = cell._tc.get_or_add_tcPr()
            shade = OxmlElement('w:shd'); shade.set(qn('w:fill'), '173844' if i == 0 else ('F2F6F7' if i % 2 else 'FFFFFF')); props.append(shade)
            borders = OxmlElement('w:tcBorders')
            for side in ('top', 'left', 'bottom', 'right'):
                border = OxmlElement('w:' + side)
                for key, val in [('val','single'), ('sz','4'), ('color','D9D9D9')]:
                    border.set(qn('w:' + key), val)
                borders.append(border)
            props.append(borders)
            for p in cell.paragraphs:
                p.paragraph_format.space_before = Pt(2 if audience == 'member' else 4)
                p.paragraph_format.space_after = Pt(2 if audience == 'member' else 4)
                for run in p.runs:
                    run.font.size = Pt(10)
                    if i == 0:
                        run.bold = True; run.font.color.rgb = RGBColor(255,255,255)
    if len(book['index']) < 20:
        doc.add_heading('看懂每页的操作提示', 2)
        doc.add_paragraph('入口告诉你先打开哪里；编号按真实点击顺序排列；截图只保留关键区域；完成检查说明怎样判断成功。保存草稿、提交申请和公开发布不是同一种结果。')
    else:
        doc.add_paragraph('操作路线：入口 → 编号步骤 → 对照截图 → 完成检查。保存不等于公开。', 'Caption')
    p = doc.add_paragraph(); p.add_run('求助入口  ').bold = True
    link(p, 'heuesta.cn/feedback/', 'https://heuesta.cn/feedback/')
    p.add_run('  网站打不开时在 QQ 群 1081376858 联系站务。')
    for n, page in enumerate(book['pages'], 1):
        ref = page['ref']; meta, _ = article(ref)
        p = doc.add_paragraph(f'任务 {n:02d} / {len(book["pages"]):02d}', 'Subtitle')
        p.paragraph_format.page_break_before = True
        bookmark(doc.add_heading(page['title'], 1), f'task_{n}')
        if page['title'] == '提交网站问题与建议':
            bookmark(p, 'feedback_task')
        goal = page.get('goal', meta['summary'])
        markdown.extend(['', f'<a id="task-{n}"></a>', f'## {n:02d} {page["title"]}', '', goal, ''])
        p = doc.add_paragraph(); p.add_run('目标  ').bold = True; inline(p, goal)
        route = page.get('route') or (meta['routes'][0] if meta.get('routes') else '/help/')
        target = route if route.startswith('https://') else 'https://heuesta.cn' + route
        entry = page.get('entry', target.removeprefix('https://'))
        p = doc.add_paragraph(style='Caption'); p.add_run('入口  ').bold = True
        link(p, entry, target)
        markdown.extend([f'入口：[{entry}]({target})', ''])
        if 'lead' in page:
            lead = page['lead']
            lines = excerpt(lead['ref'], lead['section'], lead.get('items'))
            p = doc.add_paragraph(); p.add_run('开始前  ').bold = True; inline(p, ' '.join(lines))
            markdown.extend(lines + [''])
        lines = []
        for selection in page['sections']:
            lines.extend(excerpt(ref, selection[0], selection[1] if len(selection)>1 else None))
        add_lines(doc, lines)
        markdown.extend([f'{i}. {line}' for i, line in enumerate(lines, 1)] + [''])
        image_ref = page.get('image_ref', ref)
        image_meta, _ = article(image_ref)
        image_date = page.get('image_verified', '2026-09-05' if page['image'] == 'workspace-page.png' else image_meta['verified'])
        for key in ('image','image2'):
            if key not in page:
                continue
            name = page[key]
            if name not in image_meta['screenshots']:
                raise ValueError(f'{image_ref} does not declare {name}')
            number = image_meta['screenshots'].index(name) + 1
            description = page.get('image_label', page['title'] + ' 操作区')
            label = f'图 {n:02d}-{1 if key == "image" else 2}  {description}'
            image_data = add_picture(doc, name, label, max_height=page.get('image_height', 55 if 'image2' in page else 90))
            image_data.update(article=image_ref, screenshot_number=f'{image_meta["order"]}-{number}', verified=image_date)
            evidence.append(image_data)
            asset_path = Path(os.path.relpath(ASSETS / name, OUT)).as_posix()
            markdown.extend([f'![{label}]({asset_path})', ''])
        if 'extra' in page:
            extra = page['extra']; lines = excerpt(extra['ref'], extra['section'], extra.get('items'))
            p = doc.add_paragraph(); p.add_run(page.get('extra_label', '接下来') + '  ').bold = True; inline(p, ' '.join(lines))
            markdown.extend(lines + [''])
        p = doc.add_paragraph(); p.add_run('完成检查  ').bold = True
        inline(p, '□ ' + meta['checkpoints'][page.get('check', 0)])
        _, sections = article(ref)
        trouble = next(iter(sections.get('遇到问题', [])), '')
        if trouble and not page.get('omit_trouble'):
            p = doc.add_paragraph(); inline(p, trouble.removeprefix('- '))
            markdown.append(trouble)
        p = doc.add_paragraph(style='Caption')
        p.add_run(f'来源 {ref}  |  图源日期 {image_date}  |  图源 {image_meta["order"]}-{image_meta["screenshots"].index(page["image"])+1}  ')
        link(p, '详细帮助与原图', f'https://heuesta.cn/help/{ref}/')
        if page.get('finish'):
            p.add_run('  '); link(p, '账号安全与后续任务', 'https://heuesta.cn/help/' + page['finish'] + '/')
        markdown.extend(['', '完成检查：□ ' + meta['checkpoints'][page.get('check', 0)],
                         f'[详细帮助](https://heuesta.cn/help/{ref}/)', '[返回目录](#任务目录)', ''])
    OUT.mkdir(parents=True, exist_ok=True)
    stem = edition_stem(config, audience)
    doc.save(OUT / f'{stem}.docx')
    (OUT / f'{stem}.md').write_text('\n'.join(markdown), encoding='utf-8')
    return {'book':stem,'source_revision':revision,'site_version':config['site_version'],
            'verified':config['verified'],'expected_pages':len(book['pages'])+3,'images':evidence}


def main():
    global OUT
    parser = argparse.ArgumentParser(); parser.add_argument('--inventory', action='store_true')
    parser.add_argument('--audience', choices=AUDIENCES, help='Rebuild only this audience, preserving other editions.')
    args = parser.parse_args()
    config = json.loads(MANIFEST.read_text(encoding='utf-8'))
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', config['verified']):
        raise ValueError('Invalid revision date')
    OUT = OUT / config['verified']
    if args.inventory:
        inventory(config); return
    revision = subprocess.check_output(['git','rev-parse','--short','HEAD'], cwd=ROOT, text=True).strip()
    audiences = (args.audience,) if args.audience else AUDIENCES
    results = [make_book(config, audience, revision) for audience in audiences]
    evidence_path = OUT / 'first-use-evidence.json'
    previous = json.loads(evidence_path.read_text(encoding='utf-8')) if args.audience and evidence_path.exists() else []
    evidence = {item['book']: item for item in previous}
    evidence.update({item['book']: item for item in results})
    combined = [evidence[edition_stem(config, name)] for name in AUDIENCES if edition_stem(config, name) in evidence]
    evidence_path.write_text(json.dumps(combined, ensure_ascii=False, indent=2), encoding='utf-8')
    for item in results:
        print(f'{item["book"]}: {item["expected_pages"]} planned pages; {len(item["images"])} screenshots')


if __name__ == '__main__':
    main()
