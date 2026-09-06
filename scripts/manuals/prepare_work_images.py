"""Prepare lossless manual crops from the isolated works browser walkthrough."""
from pathlib import Path

from PIL import Image

from prepare_revision_images import annotated

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / '.shots/member-works'
OUT = ROOT / 'app/helpcenter/assets'


def main():
    for source, target in (
        ('editor-form.png', 'manual-works-upload.png'),
        ('publish-confirm.png', 'manual-works-publication.png'),
    ):
        with Image.open(SOURCE / source) as image:
            image.save(OUT / target, optimize=True)
    # The tested visitor viewport is 1280px; retain the filter and complete first card.
    with Image.open(SOURCE / 'wall-published-1440.png') as image:
        box = (46, 430, 442, 943)
        assert image.width == 1280 and image.height >= box[3], 'Recapture or review crop after viewport changes'
        cropped = image.convert('RGB').crop(box)
        annotated(cropped, '发布结果：作品墙中的公开卡片').save(
            OUT / 'manual-works-published-result.png', optimize=True)
    print('Prepared upload, consent, and published-wall screenshots from isolated browser captures.')


if __name__ == '__main__':
    main()
