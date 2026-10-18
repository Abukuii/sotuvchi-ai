import io

from django.contrib.auth.models import User
from django.test import TestCase
from openpyxl import Workbook

from shops.models import Shop

from .importer import ImportErrorBase, build_template_xlsx, import_catalog
from .models import Product
from .search import search_products
from .text import detect_language, keywords, normalize


def make_shop(username="owner"):
    user = User.objects.create_user(username, password="pass12345!")
    return Shop.objects.create(owner=user, name=f"{username} do'koni")


def make_xlsx(rows):
    wb = Workbook()
    ws = wb.active
    for row in rows:
        ws.append(row)
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


class TextTests(TestCase):
    def test_normalize_unifies_alphabets(self):
        self.assertEqual(normalize("Ko'ylak"), normalize("кўйлак"))
        self.assertEqual(normalize("Ko‘ylak"), "koylak")

    def test_keywords_drop_stopwords(self):
        self.assertEqual(keywords("Salom, ko'ylak narxi qancha?"), ["koylak"])

    def test_detect_language(self):
        self.assertEqual(detect_language("Привет, сколько стоит?"), "ru")
        self.assertEqual(detect_language("Салом, қанча?"), "uz")
        self.assertEqual(detect_language("Salom"), "uz")
        self.assertEqual(detect_language("ok", default="ru"), "ru")


class SearchTests(TestCase):
    def setUp(self):
        self.shop = make_shop()
        import_catalog(self.shop, "k.xlsx", build_template_xlsx())

    def test_finds_across_alphabets_and_suffixes(self):
        for query in ["ko'ylak bormi", "кўйлак", "koylaklar", "Ko'ylakni olaman"]:
            hits = search_products(self.shop, query)
            self.assertTrue(hits, query)
            self.assertEqual(hits[0].product.sku, "KY-001", query)

    def test_phone_number_does_not_match_products(self):
        self.assertEqual(search_products(self.shop, "+998 90 123 45 67"), [])

    def test_number_alone_is_not_a_match(self):
        self.assertEqual(search_products(self.shop, "45"), [])

    def test_inactive_products_hidden(self):
        Product.objects.filter(shop=self.shop).update(is_active=False)
        self.assertEqual(search_products(self.shop, "ko'ylak"), [])

    def test_other_shop_isolated(self):
        other = make_shop("other")
        self.assertEqual(search_products(other, "ko'ylak"), [])


class ImporterTests(TestCase):
    def setUp(self):
        self.shop = make_shop()

    def test_template_import(self):
        result = import_catalog(self.shop, "k.xlsx", build_template_xlsx())
        self.assertEqual((result.created, result.updated, result.skipped), (3, 0, 0))

    def test_reimport_updates_by_sku(self):
        import_catalog(self.shop, "k.xlsx", build_template_xlsx())
        data = make_xlsx([["Nomi", "Narxi", "Kod"], ["Yangi nom", 99000, "KY-001"]])
        result = import_catalog(self.shop, "k.xlsx", data)
        self.assertEqual((result.created, result.updated), (0, 1))
        self.assertEqual(Product.objects.get(shop=self.shop, sku="KY-001").price, 99000)
        self.assertEqual(Product.objects.filter(shop=self.shop).count(), 3)

    def test_price_formats(self):
        data = make_xlsx([["nom", "narx", "qoldiq"], ["A", "12 500 so'm", "3"], ["B", "12.500", 1], ["C", "1500,5", None]])
        result = import_catalog(self.shop, "k.xlsx", data)
        self.assertEqual(result.created, 3)
        self.assertEqual(Product.objects.get(name="A").price, 12500)
        self.assertEqual(Product.objects.get(name="B").price, 12500)
        self.assertEqual(Product.objects.get(name="C").stock, 0)

    def test_bad_rows_reported_not_fatal(self):
        data = make_xlsx([["Nomi", "Narxi"], ["OK", 1000], ["", 500], ["Xato narx", "abc"], ["Manfiy", -5]])
        result = import_catalog(self.shop, "k.xlsx", data)
        self.assertEqual(result.created, 1)
        self.assertEqual(result.skipped, 3)
        self.assertEqual(len(result.errors), 3)

    def test_russian_headers(self):
        data = make_xlsx([["Название", "Цена", "Остаток"], ["Рубашка", 100000, 4]])
        self.assertEqual(import_catalog(self.shop, "k.xlsx", data).created, 1)

    def test_missing_columns(self):
        with self.assertRaises(ImportErrorBase):
            import_catalog(self.shop, "k.xlsx", make_xlsx([["Foo", "Bar"], [1, 2]]))

    def test_wrong_extension_and_garbage(self):
        with self.assertRaises(ImportErrorBase):
            import_catalog(self.shop, "k.exe", b"MZ")
        with self.assertRaises(ImportErrorBase):
            import_catalog(self.shop, "k.xlsx", b"not an excel file")

    def test_csv(self):
        data = "Nomi;Narxi;Qoldiq\nKrossovka;300000;2\n".encode("utf-8")
        self.assertEqual(import_catalog(self.shop, "k.csv", data).created, 1)

    def test_too_large(self):
        with self.settings(MAX_UPLOAD_BYTES=10):
            with self.assertRaises(ImportErrorBase):
                import_catalog(self.shop, "k.xlsx", build_template_xlsx())
