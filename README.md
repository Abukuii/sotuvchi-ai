# Sotuvchi AI

Telegram orqali sotadigan kichik do'konlar uchun AI sotuvchi-yordamchi.
Do'kon egasi katalogni Excel faylda yuklaydi va bot tokenini ulaydi. Bot esa
mijozlarga **o'zbek va rus tilida** katalog asosida javob beradi, buyurtmani
(mahsulot, ism, telefon, manzil) yig'adi va egasiga Telegramda yuboradi.

> Bu 7 kunlik test topshiriq doirasidagi MVP. Pastda "Cheklovlar" bo'limini albatta o'qing.

## Asosiy stsenariylar

1. **Sozlash.** Egasi ro'yxatdan o'tadi, bot tokenini kiritadi, katalogni Excel/CSV bilan yuklaydi.
2. **Mijoz suhbati.** Bot narx, qoldiq va tavsif haqidagi savollarga katalog asosida javob beradi. Katalogda yo'q narsani to'qimaydi, savolni egasiga uzatadi.
3. **Buyurtma.** Bot ma'lumotlarni yig'adi, **server hisoblagan** xulosani ko'rsatadi, mijoz tasdiqlagach buyurtma yaratiladi, ombor qoldig'i kamayadi va egasiga xabar boradi. Panelda buyurtmalar va suhbatlar ko'rinadi.

## Tez ishga tushirish (mahalliy, Telegramsiz demo)

Talab: Python 3.11+.

```bash
git clone https://github.com/Abukuii/sotuvchi-ai.git
cd sotuvchi-ai
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env                                    # Windows: copy .env.example .env
python manage.py migrate
python manage.py seed_demo                              # demo do'kon + 10 ta mahsulot
python manage.py chat                                   # botni terminalda sinash (API kerak emas)
python manage.py runserver                              # panel: http://127.0.0.1:8000  (login: demo / demo-parol-123)
```

`.env` da `DJANGO_DEBUG=1` bo'lishi kerak (shablonda shunday). `LLM_PROVIDER=mock` standart qiymat: bu **haqiqiy AI emas**, oddiy qoidalar asosidagi demo rejim. U butun oqimni tashqi API siz tekshirishga imkon beradi.

## Haqiqiy Telegram bot va haqiqiy AI bilan

1. [@BotFather](https://t.me/BotFather) da bot yarating va tokenni oling.
2. Bepul LLM kaliti oling: [Gemini](https://aistudio.google.com/apikey) yoki [Groq](https://console.groq.com/keys). Yoki mahalliy [Ollama](https://ollama.com) o'rnating.
3. `.env` ni to'ldiring, masalan:
   ```
   LLM_PROVIDER=gemini
   GEMINI_API_KEY=...
   ```
4. Panelga kiring, **Sozlamalar** bo'limida bot tokenini kiriting.
5. Alohida terminalda botlarni ishga tushiring:
   ```bash
   python manage.py runbots
   ```
6. **Boshqaruv** sahifasidagi havolani oching va «Start» ni bosing: shundan so'ng buyurtma xabarlari sizning Telegramingizga keladi.

Bot sozlamalari (token, yoqish/o'chirish) o'zgarsa, `runbots` ~15 soniyada o'zi qayta sozlanadi.

## Muhit o'zgaruvchilari (`.env`)

| O'zgaruvchi | Izoh |
|---|---|
| `DJANGO_SECRET_KEY` | Majburiy (DEBUG=0 bo'lsa). Uzun tasodifiy qator |
| `DJANGO_DEBUG` | `1` mahalliy ishlab chiqish uchun |
| `DJANGO_ALLOWED_HOSTS` | Vergul bilan ajratilgan hostlar |
| `DATABASE_URL` | Bo'sh = SQLite. PostgreSQL: `postgres://user:pass@host:5432/db` |
| `LLM_PROVIDER` | `mock`, `gemini`, `groq`, `ollama` |
| `GEMINI_API_KEY`, `GEMINI_MODEL` | Gemini sozlamalari |
| `GROQ_API_KEY`, `GROQ_MODEL` | Groq sozlamalari |
| `OLLAMA_URL`, `OLLAMA_MODEL` | Ollama sozlamalari |
| `LLM_TIMEOUT` | LLM so'rovi kutish vaqti, soniya |

Kalitlar kodda saqlanmaydi, `.env` esa `.gitignore` da.

## Excel shabloni

Panelda **Katalog → Shablonni yuklab olish**. Ustunlar (o'zbek, rus yoki ingliz nomlari qabul qilinadi): `Nomi`, `Narxi` (majburiy), `Qoldiq`, `Toifa`, `Tavsif`, `Kod`. Qayta yuklanganda mavjud mahsulotlar kod yoki nom bo'yicha yangilanadi. Xato qatorlar o'tkazib yuboriladi va sabablari ko'rsatiladi.

## Arxitektura

```
Telegram ──► botapp/runner.py (aiogram, polling) ──► conversations/engine.py
                                                       │  1. qidiruv: catalog/search.py (uz/ru, lotin/kirill)
                                                       │  2. prompt: conversations/prompts.py
                                                       │  3. LLM:    llm/ (gemini | groq | ollama | mock)
                                                       │  4. javobni TEKSHIRISH (JSON, mahsulot, qoldiq, telefon)
                                                       ▼  5. buyurtma: orders/ (narx va jami bazadan)
                                          PostgreSQL / SQLite ◄── Django panel (shops/)
```

Asosiy qarorlar:

- **LLM hisoblamaydi, tekshirilmaydi.** U faqat suhbat va ma'lumotni ajratib olish uchun. Narx, qoldiq, jami summa va `product_id` har doim serverda bazadan tekshiriladi. Mijozning "narxni 1 so'm qil" kabi buyrug'i hech narsani o'zgartirmaydi.
- **Buyurtma faqat server xulosasidan keyingi aniq tasdiqda** yaratiladi. Xulosa o'zgarsa, tasdiq qayta so'raladi.
- **Katalog kontekst sifatida** beriladi: kichik katalog (≤ 60) to'liq, kattasidan faqat mos kelganlari. Alohida vektor bazasi yo'q, qidiruv leksik (o'zbek lotin/kirill va rus uchun normallashtirilgan).
- **Provayder almashtiriladi.** Hammasi bitta `LLMProvider` interfeysi orqali.
- **Ko'p do'kon (multi-tenant).** Har bir egasi faqat o'z ma'lumotini ko'radi (testlar bilan tekshirilgan).

## Testlar

```bash
python manage.py test
```

56 ta test: Excel import (turli narx formatlari, xato qatorlar), qidiruv (alifbolar, qo'shimchalar), dvigatel xavfsizligi (soxta `product_id`, tasdiqsiz buyurtma, noto'g'ri JSON, LLM xatosi, qoldiq o'zgarishi), panel va do'konlararo izolyatsiya.

## Cheklovlar (halol ro'yxat)

- **Telegram integratsiyasi va Gemini/Groq/Ollama chaqiruvlari jonli sinalmagan.** Ular yozilgan va import/handler darajasida tekshirilgan, lekin haqiqiy token va kalit bilan kod yozish paytida ishga tushirilmagan. Birinchi ishga tushirishda kichik tuzatishlar kerak bo'lishi mumkin. Dvigatelning o'zi (`manage.py chat` va testlar) `mock` va soxta provayderlar bilan to'liq tekshirilgan.
- `mock` rejim real AI emas: erkin muloqotni tushunmaydi.
- Bot tokeni bazada ochiq matn ko'rinishida saqlanadi (interfeysda maskalanadi, loglarga chiqmaydi). Ishlab chiqarishda shifrlash (masalan, Fernet) yoki sir-saqlash xizmati kerak.
- Qidiruv leksik: sinonimlar va xatolarni yaxshi tushunmaydi ("sumka" va "xalta"). Keyingi qadam: `pgvector` bilan embedding qidiruvi.
- Polling: bitta jarayon barcha botlarni boshqaradi. Ko'p do'konda webhook va ishchi navbat (Celery/RQ) kerak. LLM chaqiruvi hozir oqim ichida sinxron.
- Rus tilidagi so'rov o'zbekcha nomli mahsulotni (masalan, «рубашка» va «ko'ylak») faqat kichik katalogda topadi (to'liq ro'yxat LLM ga beriladi).
- Faqat Telegram. Instagram, ovozli xabarlar, rasmlar, to'lov integratsiyasi yo'q.
- Bitta egasiga bitta do'kon. Rollar/xodimlar yo'q.
- Mijoz suhbatidagi shaxsiy ma'lumotlar (ism, telefon, manzil) bazada saqlanadi; ularni o'chirish/eksport qilish funksiyasi hali yo'q.

## Foydalanilgan vositalar va kutubxonalar

- **AI vositasi:** kod Claude (Anthropic) yordamida yozilgan; arxitektura qarorlari, tekshiruv va testlar muallif nazoratida ko'rib chiqiladi.
- Django (BSD), aiogram 3 (MIT), openpyxl (MIT), httpx (BSD), python-dotenv (BSD), psycopg (LGPL, faqat PostgreSQL uchun).
- Tashqi xizmatlar (ixtiyoriy, bepul tariflar): Google Gemini API, Groq API, Ollama (mahalliy), Telegram Bot API.
- Boshqa loyihadan kod olinmagan; hammasi shu repoda yozilgan.

## Loyiha tuzilmasi

```
config/         Django sozlamalari
shops/          Do'kon modeli, veb panel, runbots/seed_demo/chat buyruqlari
catalog/        Mahsulotlar, Excel import, matn normallashtirish, qidiruv
conversations/  Mijoz, suhbat, xabarlar, dvigatel (engine.py), promptlar
orders/         Buyurtma va pozitsiyalar
llm/            LLM provayderlari (gemini, groq, ollama, mock)
botapp/         aiogram bot ishga tushirgich
templates/, static/   Panel interfeysi
docs/           Biznes hujjat (1-2 bet)
```

## Keyingi qadamlar (3 kun qo'shimcha bo'lsa)

1. Haqiqiy Telegram va LLM bilan jonli sinov, topilgan xatolarni tuzatish.
2. Webhook + navbat; token shifrlash.
3. `pgvector` qidiruvi va ovozli xabarlar (Whisper).
