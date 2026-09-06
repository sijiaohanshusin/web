"""Lossless crops of isolated browser evidence, never production member data."""
from pathlib import Path

from PIL import Image

from prepare_revision_images import annotated

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.shots/achievements'
OUT = ROOT / 'app/helpcenter/assets'


def main():
    items = (
        ('contributors.png', 'manual-contributors.png', '共同署名：选准确用户名，未注册者留空', None),
        ('honor-fields.png', 'manual-honor-fields.png', '关联已公开作品；证书上传前先脱敏', (0, 525, 858, 774)),
        ('honor-consent.png', 'manual-honor-consent.png', '核对预览 → 勾选同意 → 本人发布', None),
        ('claim-review.png', 'manual-claim-review.png', '核实参与事实 → 填写结论 → 关联或拒绝', (264, 275, 1405, 635)),
        ('honor-ranking.png', 'manual-honor-ranking.png', '重要性与精选只改变排列，不代替作者公开', None),
    )
    for source, target, label, box in items:
        with Image.open(SOURCE / source) as original:
            image = original.convert('RGB')
            if box:
                assert 0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height
                image = image.crop(box)
            annotated(image, label).save(OUT / target, optimize=True)
    # Split one long phone form into two explicitly labelled reading panels.
    # Preserve its original pixels; do not reconstruct controls or blank inputs.
    with Image.open(SOURCE / 'claim-form.png') as source:
        image = source.convert('RGB')
        split = 325
        left = annotated(image.crop((0, 0, image.width, split)), '① 选择署名与填写分工')
        right = annotated(image.crop((0, split, image.width, image.height)), '② 说明事实与确认提交')
        sheet = Image.new('RGB', (left.width + right.width + 16, max(left.height, right.height)), '#eef5f6')
        sheet.paste(left, (0, 0))
        sheet.paste(right, (left.width + 16, 0))
        sheet.save(OUT / 'manual-claim-form.png', optimize=True)
    print('Prepared six annotated screenshots from isolated workflow evidence.')


if __name__ == '__main__':
    main()
