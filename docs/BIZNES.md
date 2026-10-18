# Sotuvchi AI: biznes hujjat

## Muammo
Telegram va Instagram orqali sotadigan kichik do'konlarda egasi (yoki bitta sotuvchi) kun bo'yi bir xil savollarga javob beradi: "narxi qancha", "razmeri bormi", "yetkazib berasizmi". Kechqurun va tunda yozgan mijozlar javob kutmay ketadi, buyurtmalar daftar, Telegram yozishmalari va Excel orasida yo'qoladi.

## Kim uchun (birinchi mijoz)
Kuniga 10-100 ta yozishma oladigan, 20-300 ta mahsuloti bor, hodimi yo'q yoki 1-2 ta hodimi bor onlayn do'kon egasi: kiyim, poyabzal, kosmetika, aksessuar, bolalar mollari, oziq-ovqat. Ularning katalogi allaqachon Excel yoki Telegram kanalda bor, shuning uchun 5 daqiqada ishga tushadi.

## Yechim va farqi
Egasi Excel yuklaydi va bot tokenini ulaydi. Bot o'zbek va rus tilida katalog asosida javob beradi, buyurtmani yig'adi va egasiga tayyor holda yuboradi.

| | Sotuvchi AI | Bot konstruktorlar (ManyChat, Chatfuel va h.k.) | Oddiy ChatGPT/Gemini |
|---|---|---|---|
| O'zbek va rus tilida erkin muloqot | Ha (LLM) | Asosan qo'lda yozilgan stsenariy | Ha |
| Do'kon narxi va qoldig'ini biladi | Ha, Excel dan | Faqat qo'lda kiritilsa | Yo'q |
| Buyurtmani yig'ib egasiga yuboradi | Ha | Stsenariy tuzilsa | Yo'q |
| Narxni to'qimaydi | Narx/qoldiq serverda bazadan | Stsenariyga bog'liq | Xavf bor |
| Sozlash | Excel + token, ~5 daqiqa | Stsenariy qurish kerak | Mumkin emas |

> **Tekshirilishi kerak:** konstruktorlarning aniq narxi va imkoniyatlarini (shu jumladan mahalliy xizmatlarni, masalan ChatPlace) taqdimotdan oldin ularning rasmiy saytlaridan tekshirib, jadvalni yangilash kerak. Yuqoridagi taqqoslash umumiy tavsif, tekshirilgan raqamlar emas.

Asosiy farq: **sozlash soddaligi + mahalliy tillar + AI ning narx/qoldiqni o'zgartira olmasligi** (xavfsizlik serverda).

## Pul modeli (gipoteza, bozorda tekshirilmagan)
- Oylik obuna: **300 000 so'm/oy** (1 do'kon, 1 bot, 500 ta mahsulotgacha), **500 000 so'm/oy** (cheksiz mahsulot, Instagram qo'shilganda).
- 14 kun bepul sinov. Birinchi 10 mijozga o'rnatishni bepul qilish.
- Mantiq: kuniga kamida 1 soat yozishmaga ketadigan do'kon egasi uchun va bitta yo'qotilgan buyurtma narxi obuna narxiga yaqin.
- Xarajat: bepul LLM tariflari bilan boshlanadi; mijozlar ko'paysa, LLM xarajati bitta do'konga oyiga taxminan bir necha dollar bo'lishi kutilmoqda (kuzatib o'lchash kerak).

## Birinchi sotuvlar rejasi
1. **Hafta 1:** Jizzax va Toshkentdagi 10 ta do'kon egasiga Telegramda shaxsan yozish, 5 daqiqalik demo (o'zining katalogi bilan) ko'rsatish.
2. **Hafta 2-3:** 3-5 ta do'konga bepul ulash, buyurtma soni va tejalgan vaqtni o'lchash, ruxsat bilan keys tayyorlash.
3. **Hafta 4+:** Telegram kanallar va sotuvchilar guruhlarida keys bilan e'lon, har bir mijozdan tavsiya so'rash, kichik biznes hamjamiyatlarida taqdimot.

## Asosiy xavflar
- **AI xatosi:** noto'g'ri javob ishonchni buzadi. Chorasi: faqat katalogdan javob, noaniq savol egasiga uzatiladi, buyurtma tasdiqlanadi.
- **O'zbek tili sifati:** modellar orasida farq katta. Chorasi: haqiqiy suhbatlar bilan sinab modelni tanlash.
- **Bepul API limitlari:** mijozlar ko'paysa, pullik tarif va navbat kerak.
- **Platforma xavfi:** faqat Telegram Bot API ga bog'liqlik; Instagram uchun alohida ruxsatlar kerak.
- **Maxfiylik:** mijozlar ism/telefon/manzili saqlanadi; shifrlash va o'chirish funksiyasi kerak (hozircha yo'q).

## Muvaffaqiyat o'lchovlari (birinchi 30 kun)
Sinovdagi do'konlarning kamida 3 tasi pullik rejaga o'tadi; bot hal qilgan suhbatlar ulushi (egasiga uzatilmagan) 60% dan yuqori; o'rtacha javob vaqti 10 soniyadan kam.
