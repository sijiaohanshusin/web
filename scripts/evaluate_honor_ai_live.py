"""Explicit, bounded live evaluation; no database, website writes or automatic retries.

Pass up to six certificate paths and --live. The key is read with echo disabled,
never from command-line arguments, and the report stays under ignored .shots/.
The same upload encoder, prompt, transport and normalizer as the app are used.
This isolated operator test does NOT turn on the application's free-tier gates.
"""
import argparse
from datetime import datetime, timezone
import getpass
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace
import warnings

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='+', type=Path)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--model', default='qwen3.8-max-0902')
    parser.add_argument('--label', default='originals')
    args = parser.parse_args()
    if not args.live or not 1 <= len(args.images) <= 6:
        parser.error('Explicit --live and 1 to 6 images are required.')
    sys.stdout.reconfigure(encoding='utf-8')
    sys.path.insert(0, str(ROOT / 'app'))
    os.environ.update(DJANGO_SETTINGS_MODULE='config.settings.dev', HONOR_AI_ENABLED='0',
                      DASHSCOPE_API_KEY='', DASHSCOPE_WORKSPACE_ID='')
    import django
    django.setup()
    from django.conf import settings
    from django.core.files.base import ContentFile
    from achievements import recognition
    from showcase.services import encode_image
    if args.model not in recognition.MODELS:
        parser.error('Model is not in the application allowlist.')
    if not args.label.isascii() or not args.label.replace('-', '').isalnum():
        parser.error('Use an ASCII alphanumeric report label.')

    # Validate every file before making any chargeable request.
    samples = []
    for index, path in enumerate(args.images, 1):
        with path.open('rb') as source:
            raw = source.read(5 * 1024 * 1024 + 1)
        encoded, size = encode_image(ContentFile(raw, name=path.name))[0]
        samples.append((f'case-{index}', hashlib.sha256(raw).hexdigest(), encoded, size))
    print(f'LIVE: {len(samples)} requests maximum; model={args.model}; official Beijing endpoint.', flush=True)
    with warnings.catch_warnings():
        warnings.simplefilter('error', getpass.GetPassWarning)
        key = getpass.getpass('Temporary key (hidden): ')
    if not key.strip():
        parser.error('Empty key; no request sent.')
    settings.DASHSCOPE_API_KEY = key.strip()
    key = None
    report = {'started_at': datetime.now(timezone.utc).isoformat(), 'model': args.model,
              'endpoint': recognition.model_endpoint(), 'prompt_version': recognition.PROMPT_VERSION,
              'max_output_tokens_per_request': 2048, 'automatic_retries': 0,
              'production_enabled': False, 'cases': []}
    output = ROOT / '.shots' / 'honor-ai-live' / (
        datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + args.label + '.json')
    output.parent.mkdir(parents=True, exist_ok=True)
    try:
        for case_id, digest, encoded, size in samples:
            case = {'id': case_id, 'sha256': digest, 'processed_size': size, 'bytes': len(encoded)}
            task = SimpleNamespace(model=args.model, certificate=SimpleNamespace(
                image=ContentFile(encoded, name='certificate.jpg')))
            started = time.monotonic()
            try:
                raw, usage = recognition.call_model(task)
                case.update(http_status=200, usage=usage)
                # Only schema fields, no arbitrary raw provider response or unknown keys.
                case['extracted'] = {k: raw.get(k) for k in recognition.SCHEMA} if isinstance(raw, dict) else {}
                case.update(status='success', result=recognition.normalize_result(raw, image_size=size))
            except recognition.RecognitionError as exc:
                case.update(status='failed', error=exc.code)
            case['seconds'] = round(time.monotonic() - started, 2)
            report['cases'].append(case)
            output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
            print(json.dumps(case, ensure_ascii=False), flush=True)
            if case['status'] == 'failed':
                print('Stopped: no automatic retry or model fallback.', flush=True)
                break
    finally:
        settings.DASHSCOPE_API_KEY = ''
    print(f'Report: {output}', flush=True)
    return 0 if len(report['cases']) == len(samples) and all(
        c['status'] == 'success' for c in report['cases']) else 1


if __name__ == '__main__':
    raise SystemExit(main())
