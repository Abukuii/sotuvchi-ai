from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from catalog.models import Product
from shops.models import Shop

DEMO_PRODUCTS = [
    ("KY-001", "Erkaklar ko'ylagi (oq)", "Kiyim", 180000, 12, "Paxta, razmerlar: S, M, L, XL"),
    ("KY-002", "Erkaklar ko'ylagi (ko'k)", "Kiyim", 195000, 7, "Paxta, razmerlar: M, L, XL"),
    ("PL-010", "Ayollar ko'ylagi (gulli)", "Kiyim", 260000, 6, "Yozgi, razmerlar: 42-48"),
    ("SM-014", "Ayollar sumkasi", "Aksessuar", 250000, 5, "Haqiqiy teri, qora rang"),
    ("KR-220", "Krossovka Run Pro", "Poyabzal", 420000, 8, "Razmerlar 40-45, yengil taglik"),
    ("KR-221", "Krossovka City", "Poyabzal", 350000, 0, "Razmerlar 38-44 (hozir tugagan)"),
    ("JN-030", "Jinsi shim klassik", "Kiyim", 310000, 15, "Razmerlar 30-38"),
    ("SO-005", "Paypoq to'plami (5 juft)", "Aksessuar", 45000, 40, "Paxta, uniseks"),
    ("KP-002", "Qishki kurtka", "Kiyim", 780000, 4, "Issiq, suv o'tkazmaydi, M-XXL"),
    ("BR-001", "Teri kamar", "Aksessuar", 95000, 20, "Qora va jigarrang"),
]


class Command(BaseCommand):
    help = "Demo foydalanuvchi, do'kon va namunaviy katalog yaratadi (qayta ishga tushirsa ham xavfsiz)."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="demo")
        parser.add_argument("--password", default="demo-parol-123")

    def handle(self, *args, **options):
        username, password = options["username"], options["password"]
        user, created = User.objects.get_or_create(username=username)
        if created:
            user.set_password(password)
            user.save()
        shop, _ = Shop.objects.get_or_create(
            owner=user,
            defaults={
                "name": "Demo Moda do'koni",
                "delivery_info": "Jizzax va Toshkent bo'ylab 1-2 kunda yetkaziladi. 500 000 so'mdan yuqori buyurtmada yetkazib berish bepul. To'lov: naqd yoki Click/Payme.",
                "work_hours": "Har kuni 09:00-21:00",
            },
        )
        added = 0
        for sku, name, category, price, stock, desc in DEMO_PRODUCTS:
            _, was_created = Product.objects.get_or_create(
                shop=shop, sku=sku,
                defaults={"name": name, "category": category, "price": price, "stock": stock, "description": desc},
            )
            added += was_created
        self.stdout.write(self.style.SUCCESS(f"Tayyor: {shop.name}, {added} ta yangi mahsulot."))
        if created:
            self.stdout.write(f"Kirish: login={username} parol={password}")
        else:
            self.stdout.write(f"Foydalanuvchi '{username}' avvaldan mavjud, paroli o'zgartirilmadi.")
