"""Restrict only the two identified fixtures; never delete or match by title alone."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from files.models import Resource


class Command(BaseCommand):
    help = 'Preview or restrict the two audited test files to officers.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true')
        parser.add_argument('--snapshot', type=Path)

    @transaction.atomic
    def handle(self, *args, **options):
        rows = []
        for title, size in [('test1', 56), ('test', 1817)]:
            matches = list(Resource.objects.select_for_update().filter(title=title, size=size))
            if len(matches) != 1:
                raise CommandError(f'Expected one audited {title!r} ({size} bytes); found {len(matches)}. No changes.')
            row = matches[0]
            if row.min_level not in (0, 4):
                raise CommandError('Access level changed since audit. No changes.')
            rows.append({'id': row.pk, 'title': row.title, 'size': row.size, 'file': row.file.name, 'min_level': row.min_level})
        self.stdout.write(json.dumps(rows, ensure_ascii=False, indent=2))
        if not options['apply']:
            self.stdout.write('Dry run; no changes.')
            return
        if not options['snapshot']:
            raise CommandError('--snapshot is required before applying.')
        with options['snapshot'].open('x', encoding='utf-8') as stream:
            json.dump(rows, stream, ensure_ascii=False, indent=2)
        Resource.objects.filter(pk__in=[row['id'] for row in rows]).update(min_level=Resource.MinLevel.OFFICER)
        self.stdout.write(self.style.SUCCESS('Both audited fixtures are now officer-only; files retained.'))
