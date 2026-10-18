import asyncio
import logging

from django.core.management.base import BaseCommand

from botapp.runner import supervise


class Command(BaseCommand):
    help = "Barcha faol do'konlarning Telegram botlarini ishga tushiradi (Ctrl+C bilan to'xtatiladi)."

    def add_arguments(self, parser):
        parser.add_argument("--refresh", type=int, default=15, help="Sozlamalarni tekshirish oralig'i (soniya)")

    def handle(self, *args, **options):
        logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
        self.stdout.write(self.style.SUCCESS("Botlar ishga tushmoqda... (to'xtatish: Ctrl+C)"))
        try:
            asyncio.run(supervise(options["refresh"]))
        except KeyboardInterrupt:
            self.stdout.write("To'xtatildi.")
