"""Lossless crops of CUA browser captures; headings are annotations, not UI."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.shots/first-use'
OUT = ROOT / 'app/helpcenter/assets'
FONT = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 17)


def crop(name, box):
    with Image.open(SOURCE / name) as im:
        assert 0 <= box[0] < box[2] <= im.width and 0 <= box[1] < box[3] <= im.height
        return im.convert('RGB').crop(box)


def annotated(im, label):
    canvas = Image.new('RGB', (im.width + 24, im.height + 50), '#eef5f6')
    ImageDraw.Draw(canvas).text((12, 10), label, font=FONT, fill='#153d48')
    canvas.paste(im, (12, 38))
    return canvas


def main():
    items = [
        ('feedback-viewport.png',(383,248,877,610),'manual-feedback-form.png','写清问题 → 选填联系方式 → 提交反馈'),
        ('thread-viewport.png',(383,405,881,704),'manual-feedback-thread.png','在原对话继续回复，不重复提交'),
        ('gallery-viewport.png',(278,286,816,570),'manual-gallery.png','选择图片 → 写说明 → 调整顺序'),
        ('links-viewport.png',(278,237,816,560),'manual-links.png','填写名称与 HTTPS 地址'),
        ('featured-viewport.png',(278,316,816,568),'manual-featured-work.png','先启用精选作品模块，再选择代表作'),
    ]
    for source, box, filename, label in items:
        annotated(crop(source, box), label).save(OUT / filename, optimize=True)
    left = annotated(crop('work-viewport.png',(465,301,798,503)), '① 填写作品名称与说明')
    right = annotated(crop('work-bottom-viewport.png',(465,228,798,486)), '② 选关联方式与卡片精选')
    canvas = Image.new('RGB', (left.width + right.width + 12, max(left.height, right.height)), '#eef5f6')
    canvas.paste(left,(0,0)); canvas.paste(right,(left.width+12,0))
    canvas.save(OUT / 'manual-work-fields.png', optimize=True)
    print('Prepared 6 annotated screenshots; no generated or substituted interface.')


if __name__ == '__main__':
    main()
