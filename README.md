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
| `DJANGO_SECRET_KEY` | Majburiy (DEBUG=0 bo'lsa), kamida 32 belgi; namuna qiymat qabul qilinmaydi |
| `TOKEN_ENCRYPTION_KEY` | Bot tokenlarini shifrlash kaliti (bo'sh = SECRET_KEY dan). O'zgarsa tokenlar qayta kiritiladi |
| `TELEGRAM_BOT_TOKEN` | Ixtiyoriy: bot tokeni `.env` dan (panelda token kiritilmagan do'kon uchun). Panel tokeni ustun; bitta bot — bitta do'kon |
| `TELEGRAM_BOT_SHOP_ID` | Ixtiyoriy: `.env` tokeni qaysi do'konga tegishli (bo'sh = tokeni yo'q birinchi faol do'kon) |
| `TELEGRAM_OWNER_ID` | Ixtiyoriy: egasining Telegram ID si (ulash kodisiz bildirishnoma olish) |
| `GEMINI_API_KEY` / `GROQ_API_KEY` | AI kalitlari faqat `.env` dan o'qiladi, kodda va bazada saqlanmaydi |
| `GEOCODER_ENABLED` | `1` (sukut): lokatsiyadan manzil topish (Nominatim). `0` — o'chirish |
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

## Buyurtma holati

Oqim: **Yangi → Qabul qilindi → Yuborildi → Yetkazildi**; bekor qilish Yangi/Qabul/Yuborildi dan. Oraliq bosqichni o'tkazib yuborish mumkin. Yetkazildi va Bekor qilindi — yakuniy. Bekor qilinsa, ombor qoldig'i qaytariladi (bir marta, qator qulflanadi). Har o'zgarish tarixga yoziladi (panel/Telegram), mijozga o'z tilida xabar boradi.

- **Panelda:** buyurtma sahifasida faqat mumkin bo'lgan tugmalar, bosqichlar chizig'i, tarix; ro'yxatda holat tablari (soni bilan); yon panelda yangi buyurtmalar belgisi.
- **Telegramda (egasi):** yangi buyurtma xabari tugmalar bilan keladi (Qabul / Yuborildi / Yetkazildi / Bekor). Faqat ulangan ega bosa oladi, buyurtma shu do'konniki bo'lishi shart.

## Lokatsiyadan manzil

Mijoz manzil o'rniga **📍 lokatsiya** yuborishi mumkin (manzil so'ralganda pastda "📍 Lokatsiyani yuborish" tugmasi chiqadi, menyu orqali ham, AI suhbat orqali ham). Bot koordinatani manzil matniga aylantiradi (OpenStreetMap Nominatim, bepul; ishlamasa "📍 41.29950, 69.24010" yoziladi), mijozga xulosani tasdiqlatadi. Buyurtma koordinata bilan saqlanadi: egasiga xabarda xarita havolasi va Telegram lokatsiya nuqtasi keladi, panelda "Xaritada ochish" havolasi bor. Yozilgan manzil lokatsiyadan keyin o'zgartirilsa, eski koordinata tashlanadi.

- Maxfiylik: lokatsiya faqat buyurtma uchun saqlanadi. Nominatim ga faqat koordinata ketadi (mijoz ismi/telefoni emas). `GEOCODER_ENABLED=0` bo'lsa tashqariga hech narsa ketmaydi. Mijoz ma'lumotini o'chirish buyurtma yozuvlarini (koordinata ham) saqlab qoladi.

## Jonli panel

Panel sahifani yangilamasdan ishlaydi: brauzer har ~5 soniyada yengil so'rov (`/orders/live/`) yuboradi; yangi buyurtma kelsa toast bildirishnoma, yon paneldagi belgi va sahifa sarlavhasidagi `(N)` yangilanadi, Boshqaruv/Buyurtmalar/Buyurtma sahifalari o'zi yangilanadi (Telegramda egasi holatni o'zgartirsa ham). Forma bilan ishlayotganda sahifa almashtirilmaydi, tab yashirin bo'lsa so'rov to'xtaydi, xatoda kutish oshadi, seans tugasa to'xtaydi.

## Telegram bot tugmalari

Pastki menyu (Katalog, Savat, Buyurtmalarim, Ma'lumot, Sozlamalar) va inline tugmalar: toifa → mahsulot kartochkasi (miqdor tanlash) → savat → buyurtma → tasdiqlash. Til sozlamasi (uz/ru), operatorga uzatish, "ma'lumotlarimni o'chirish". Buyruqlar: /menu /catalog /cart /orders /info /settings. Tugmalar AI ni chaqirmaydi (tez va deterministik); erkin matn esa AI ga boradi. Eski "Tasdiqlash" tugmasi o'zgargan buyurtmani tasdiqlay olmaydi (qoralama versiyasi tekshiriladi).

## Dizayn

Ochiq bosh sahifa (`/`) va boshqaruv paneli (`/panel/`). Panelda yon menyu: kompyuterda yig'iladi/kengayadi (holati eslab qolinadi), telefonda chiqib turadigan menyu (Esc va fon bosilganda yopiladi). Qorong'i mavzu birinchi, yorug' mavzu avtomatik. Palitra: qora, xiralashtirilgan oq va yorqin xakki-laym (gradient, nur, yengil animatsiya; `prefers-reduced-motion` hurmat qilinadi); testlar boshqa ranglarni rad etadi.

## Boshqaruv paneli analitikasi

Daromad, buyurtmalar, o'rtacha chek, konversiya, kunlik daromad va soatlar grafigi (SVG, tashqi kutubxonasiz), kechki (21:00–09:00) xabarlar ulushi, buyurtma holatlari, top mahsulotlar, ombor ogohlantirishlari. Davr: 7/30/90 kun, oldingi shuncha kun bilan solishtiriladi; bekor qilingan buyurtmalar daromadga kirmaydi. Interfeys faqat oq, qora va yashil ranglardan iborat (qorong'i rejim ham).

## Xavfsizlik choralari

- **Bot tokenlari bazada shifrlangan** (Fernet), interfeysda maskalanadi va hech qachon qaytarilmaydi; takroriy tokenni baza rad etadi.
- **Kirish va ro'yxatdan o'tish cheklangan:** 5 ta xato urinishdan keyin 15 daqiqa blok (IP+login), IP bo'yicha umumiy chegara, soatiga 10 ta ro'yxatdan o'tish.
- **Har bir egasi faqat o'z ma'lumotini ko'radi:** barcha ko'rinishlar do'kon bo'yicha filtrlanadi, begona obyekt 404 qaytaradi (testlangan).
- **LLM ga ishonilmaydi:** narx/qoldiq/jami bazadan, `product_id` tekshiriladi, buyurtma faqat tasdiqdan keyin, ikki marta "Ha" bitta buyurtma beradi (suhbat qatori qulflanadi), javobdagi begona havolalar olib tashlanadi.
- **Fayl yuklash:** hajm, ochilgan hajm (zip-bomba), qatorlar soni, narx/qoldiq chegaralari tekshiriladi.
- **Bot faqat shaxsiy chatlarda** javob beradi; spamga qarshi daqiqada 12 xabar chegarasi.
- **Content-Security-Policy** (`'self'` faqat, inline skript/uslubsiz), `Permissions-Policy`, shaxsiy sahifalar `no-store`; parolni panelda almashtirish (`/password/`).
- Django: CSRF, `HttpOnly`/`SameSite` cookie, `X-Frame-Options: DENY`, `nosniff`; `DEBUG=0` da secure cookie; HTTPS sozlamalari `.env` orqali yoqiladi.
- **Xavfsizlik jurnali** (`/security/`): kirish, chiqish, xato urinishlar, bloklanish, parol/token o'zgarishi, katalog yuklash, buyurtma holati. Parol va token yozilmaydi; 180 kun saqlanadi. Shu sahifadan "boshqa seanslardan chiqish" mumkin. Seans 12 soat.
- **Loglarda sirlar yashiriladi:** Telegram tokeni, Gemini/Groq kalitlari, `Authorization`, `SECRET_KEY` yakuniy log matnidan (istisno izi bilan) tozalanadi; `httpx` URL loglari o'chirilgan (Telegram URL tokenni o'z ichiga oladi).
- Mijoz ma'lumotini panelda o'chirish mumkin (buyurtma yozuvlari saqlanadi).

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
- **Ism/telefon/manzil zaxira qoidalari** (`conversations/slots.py`): LLM maydonni to'ldirmasa (masalan, yalang'och "Otabek" javobi), aniq qoidalar to'ldiradi va keyingi savolni bot o'zi beradi. LLM bergan qiymat har doim ustun.
- **Katalog kontekst sifatida** beriladi: kichik katalog (≤ 60) to'liq, kattasidan faqat mos kelganlari. Alohida vektor bazasi yo'q, qidiruv leksik (o'zbek lotin/kirill va rus uchun normallashtirilgan).
- **Provayder almashtiriladi.** Hammasi bitta `LLMProvider` interfeysi orqali.
- **Ko'p do'kon (multi-tenant).** Har bir egasi faqat o'z ma'lumotini ko'radi (testlar bilan tekshirilgan).

## Testlar

```bash
python manage.py test
```

298 ta test (SQLite va PostgreSQL da o'tgan): analitika (davr chegaralari, bekorlar, oldingi davr bilan solishtirish, kechki xabarlar ulushi), CSP/sarlavhalar, rang palitrasi (faqat oq/qora/yashil),  Excel import (narx formatlari, xato qatorlar, zip-bomba, katta qiymatlar), qidiruv (alifbolar, qo'shimchalar), dvigatel xavfsizligi (soxta `product_id`, tasdiqsiz buyurtma, ikki marta tasdiq, noto'g'ri JSON, LLM xatosi, begona havolalar), token shifrlash, kirish cheklovi, panel va do'konlararo izolyatsiya.

## Cheklovlar (halol ro'yxat)

- **Telegram integratsiyasi va Gemini/Groq/Ollama chaqiruvlari jonli sinalmagan.** Ular yozilgan va import/handler darajasida tekshirilgan, lekin haqiqiy token va kalit bilan kod yozish paytida ishga tushirilmagan. Birinchi ishga tushirishda kichik tuzatishlar kerak bo'lishi mumkin. Dvigatelning o'zi (`manage.py chat` va testlar) `mock` va soxta provayderlar bilan to'liq tekshirilgan.
- **Lokatsiya (Telegram) va Nominatim geokodlash jonli sinalmagan**: Telegram qismi soxta sessiya bilan testlangan, Nominatim chaqiruvi sinovda o'rniga qo'yilgan. Nominatim ommaviy xizmat (taxminan sekundiga 1 so'rov, `User-Agent` bilan); katta yuklama uchun o'z geokoderingizni ulang yoki `GEOCODER_ENABLED=0` qiling.
- Jonli panel WebSocket emas, qisqa so'rov (polling, ~5 soniya): kechikish bir necha soniya, har ochiq tab uchun ~12 yengil so'rov/daqiqa.
- `mock` rejim real AI emas: erkin muloqotni tushunmaydi.
- Bot tokeni shifrlangan, lekin kalit `SECRET_KEY`/`TOKEN_ENCRYPTION_KEY` dan olinadi: kalitni yo'qotsangiz tokenlarni qayta kiritasiz. Jiddiy ishlab chiqarishda sir-saqlash xizmati (Vault/KMS) yaxshiroq.
- Kirish cheklovi Django keshida (jarayon ichida). Bir nechta server bo'lsa Redis/Memcached sozlash kerak. Parolni tiklash (email) yo'q.
- PostgreSQL bilan jonli sinalmagan (testlar SQLite da). Qulflash (`select_for_update`) PostgreSQL da to'liq ishlaydi, SQLite da yozuvlar baribir ketma-ket bajariladi.
- Qidiruv leksik: sinonimlar va xatolarni yaxshi tushunmaydi ("sumka" va "xalta"). Keyingi qadam: `pgvector` bilan embedding qidiruvi.
- Polling: bitta jarayon barcha botlarni boshqaradi. Ko'p do'konda webhook va ishchi navbat (Celery/RQ) kerak. LLM chaqiruvi hozir oqim ichida sinxron.
- Rus tilidagi so'rov o'zbekcha nomli mahsulotni (masalan, «рубашка» va «ko'ylak») faqat kichik katalogda topadi (to'liq ro'yxat LLM ga beriladi).
- Faqat Telegram. Instagram, ovozli xabarlar, rasmlar, to'lov integratsiyasi yo'q.
- Bitta egasiga bitta do'kon. Rollar/xodimlar yo'q.
- Mijoz ma'lumotlari (ism, telefon, manzil, suhbat) bazada ochiq saqlanadi; panelda o'chirish bor, eksport va avtomatik saqlash muddati yo'q. Buyurtmalardagi ism/telefon o'chirilmaydi.

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
docs/           BIZNES.md (1-2 bet) va DEMO.md (demo/himoya shpargalkasi)
```

## Keyingi qadamlar (3 kun qo'shimcha bo'lsa)

1. Haqiqiy Telegram va LLM bilan jonli sinov, topilgan xatolarni tuzatish.
2. Webhook + navbat; token shifrlash.
3. `pgvector` qidiruvi va ovozli xabarlar (Whisper).
