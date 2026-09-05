"""Crop verified synthetic forum screenshots without redrawing the interface."""
import argparse
import json
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
ASSETS = ROOT / 'app/helpcenter/assets'
CROPS = {
    'forum-compose.png': ('forum-first-topic-desktop.png', (54, 499, 1385, 740)),
    'forum-compose-mobile.png': ('forum-first-topic-mobile.png', (0, 0, 390, 335)),
    'forum-reply-compose.png': ('forum-first-reply.png', (54, 499, 1385, 740)),
    'forum-topic-review.png': ('forum-queue-review.png', (79, 165, 1360, 730)),
}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('evidence', type=Path)
    args = parser.parse_args()
    evidence = args.evidence.resolve()
    report = json.loads((evidence / 'checks.json').read_text(encoding='utf-8'))
    if report['errors'] or len(report['checks']) < 30:
        raise SystemExit('A complete green real-forum run is required for final manual images')
    for source, (target, crop) in CROPS.items():
        with Image.open(evidence / source) as image:
            if image.width < crop[2] or image.height < crop[3]:
                raise SystemExit(f'Unexpected screenshot geometry: {source}')
            image.convert('RGB').crop(crop).save(ASSETS / target, optimize=True)
    # Focus on the first mail's sender and rendered body, not the fixed-height
    # frame's empty lower area. The untouched source stays in CI evidence.
    with Image.open(evidence / 'forum-mailbox.png') as image:
        if image.width < 900 or image.height < 340:
            raise SystemExit('Unexpected mailbox screenshot geometry')
        image.convert('RGB').crop((196, 0, image.width, 340)).save(ASSETS / 'forum-mailbox-preview.png', optimize=True)
    print('Prepared five crops/images; all members, posts and mail are synthetic.')


if __name__ == '__main__':
    main()
