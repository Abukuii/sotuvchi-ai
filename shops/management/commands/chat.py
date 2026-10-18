from django.core.management.base import BaseCommand, CommandError

from conversations.engine import handle_message
from shops.models import Shop


class Command(BaseCommand):
    help = "Telegramsiz, terminalda botni sinab ko'rish (demo va nosozliklarni topish uchun)."

    def add_arguments(self, parser):
        parser.add_argument("--shop", default="demo", help="Do'kon egasining username i (standart: demo)")
        parser.add_argument("--user-id", type=int, default=999000111, help="Soxta Telegram ID")

    def handle(self, *args, **options):
        shop = Shop.objects.filter(owner__username=options["shop"]).first()
        if shop is None:
            raise CommandError("Do'kon topilmadi. Avval `python manage.py seed_demo` ni ishga tushiring.")
        self.stdout.write(f"«{shop.name}» boti bilan suhbat. Chiqish: Ctrl+C yoki 'exit'.\n")
        while True:
            try:
                text = input("Siz: ").strip()
            except (EOFError, KeyboardInterrupt):
                self.stdout.write("")
                break
            if text.lower() in {"exit", "quit"}:
                break
            reply = handle_message(shop, options["user_id"], "terminal", "Terminal mijoz", text)
            self.stdout.write(f"Bot: {reply.text}\n")
            if reply.owner_notice:
                self.stdout.write(self.style.WARNING(f"[Egasiga xabar]\n{reply.owner_notice}\n"))
