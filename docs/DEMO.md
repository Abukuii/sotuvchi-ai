# Demo va himoya uchun shpargalka (5-10 daqiqa)

> Bu fayl demo oldidan o'zingiz uchun. Hamma narsani o'z so'zingiz bilan tushuntira olishingiz kerak: topshiriq aynan shuni tekshiradi.

## Oldindan tayyorlash (demodan 30 daqiqa oldin)

1. `git pull`, `pip install -r requirements.txt`, `python manage.py migrate`.
2. Haqiqiy bot: @BotFather'dan test bot, `.env` da `LLM_PROVIDER=gemini` (yoki `groq`) va kalit. Panelda tokenni kiriting, `python manage.py runbots` ni ishga tushiring.
3. Katalog: o'z Excel faylingiz yoki `python manage.py seed_demo`.
4. **Telegram orqali bitta to'liq buyurtmani oldindan sinab ko'ring.** Agar internet yoki API ishlamasa, zaxira reja: `python manage.py chat` (Telegramsiz, terminalda).
5. Ikkinchi telefon yoki Telegram Web: "mijoz" sifatida yozish uchun.

## Demo ssenariysi

| Vaqt | Nima ko'rsatiladi | Nima deyish kerak |
|---|---|---|
| 0:00-1:00 | Muammo | Kichik do'kon egasi kuniga o'nlab bir xil savollarga javob beradi, kechasi yozganlar yo'qoladi. |
| 1:00-2:30 | **Sozlash:** panelga kirish, bot tokenini ulash, Excel yuklash | 5 daqiqalik sozlash: Excel + token. Xato qatorlar sababi bilan ko'rsatiladi. |
| 2:30-5:00 | **Mijoz suhbati** Telegramda: narx savoli (o'zbekcha), keyin ruscha savol, katalogda yo'q narsa | Bot katalogdan javob beradi, yo'q narsani to'qimaydi, egasiga uzatadi. |
| 5:00-7:00 | **Buyurtma:** olaman → ism → telefon → manzil → xulosa → "Ha" | Narx va jami serverda hisoblanadi. Egasiga Telegramda xabar keldi. |
| 7:00-8:30 | Panel: buyurtma, ombor qoldig'i kamaydi, suhbat tarixi, "e'tibor kerak" | Egasi hammasini bir joyda ko'radi. |
| 8:30-10:00 | Arxitektura va narx | 300 000 so'm/oy, birinchi 10 do'kon, Jizzax va Toshkent. |

**Oldindan yozilgan video emas, jonli ko'rsating.** Savol berishsa: "Narxni 1 so'm qilib bering" deb yozib ko'rsating, bot narxni o'zgartirmasligini namoyish qilish kuchli dalil.

## Himoyadagi savollar va halol javoblar

**Qaysi qismini o'zim, qaysi qismini AI qildi?**
O'zingiz haqiqatni ayting. Tavsiya: g'oya tanlash, talablar, arxitektura qarorlari (LLM'ga ishonmaslik, serverda tekshirish, tasdiqlash oqimi), natijani tekshirish va xatolarni topish sizniki. Kodning katta qismi Claude yordamida yozildi, siz har bir qismni ko'rib chiqdingiz va testlar bilan tekshirdingiz. Buni README'da ham yozilgan. **Siz tushunmaydigan qism bo'lsa, demodan oldin kodni o'qib chiqing**: `conversations/engine.py` (asosiy mantiq), `conversations/slots.py`, `catalog/search.py`, `llm/`.

**Qanday tekshirdingiz (to'g'rilik, xavfsizlik, ma'lumot)?**
99 ta avtomatik test (`python manage.py test`). Har bir muhim himoya uchun test bor va ularni buzib ko'rib testlar yiqilishini tekshirdim. Xavfsizlik: tokenlar shifrlangan, kirish cheklangan, har bir do'kon faqat o'z ma'lumotini ko'radi, LLM narx/qoldiqni o'zgartira olmaydi, fayl yuklash cheklangan (README'dagi "Xavfsizlik choralari").

**O'sishda nima sinadi va qanday tuzatasiz?**
1) Polling bitta jarayonda: webhook + navbat (Celery/RQ). 2) LLM chaqiruvi sinxron va bepul limitli: provayder almashtirish, keshlash, pullik tarif. 3) Leksik qidiruv: `pgvector` bilan embedding. 4) Kirish cheklovi jarayon xotirasida: Redis. 5) SQLite o'rniga PostgreSQL.

**Birinchi mijoz kim va nega to'laydi?**
Kuniga 10-100 yozishma oladigan, 20-300 mahsulotli Telegram/Instagram do'koni egasi. Bir yo'qotilgan buyurtma narxi obuna narxiga yaqin. (`docs/BIZNES.md`. Narxlar gipoteza, mijozlar bilan tekshirilmagan: shuni ochiq ayting.)

**Yana 3 kun bo'lsa nima qilasiz?**
1) Haqiqiy suhbatlarda sifatni o'lchash va promptni yaxshilash (eng katta xavf shu). 2) Webhook, navbat. 3) Ovozli xabarlar (Whisper), `pgvector`. Sabab: mahsulot qiymati AI javob sifatiga bog'liq, shuning uchun avval shuni isbotlash kerak.

## Ochiq ayting (ishonchni oshiradi)

- Telegram va Gemini/Groq bilan jonli sinov qilingan sanani/natijani ayting (agar qilmagan bo'lsangiz, "faqat mock va testlarda" deb).
- `mock` rejim real AI emas.
- Raqobatchilar jadvalini saytlaridan tekshirib yangilang (`docs/BIZNES.md`).
- Foydalanilgan vositalar: Claude (kod), Django, aiogram, openpyxl, httpx, cryptography. Pullik xizmat ishlatilmagan.
