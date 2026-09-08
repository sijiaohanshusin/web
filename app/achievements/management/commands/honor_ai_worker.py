import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections

from achievements.recognition import process_one


class Command(BaseCommand):
    help = 'Process private honor recognition jobs sequentially; never publishes content.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')

    def handle(self, *args, **options):
        while True:
            close_old_connections()
            processed = process_one()
            if options['once']:
                return
            if not processed:
                time.sleep(2)
