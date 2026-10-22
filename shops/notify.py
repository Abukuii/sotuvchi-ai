"""Mijozga Telegram orqali xabar yuborish (panel tomonidan, masalan buyurtma holati o'zgarganda).

Bot jarayoni (runbots) ishlamasa ham ishlaydi: to'g'ridan-to'g'ri Telegram Bot API ga murojaat qiladi.
Tokenni loglarga yozmaslik uchun xatolarda faqat xato turi va HTTP status chiqariladi.
"""
import logging

import httpx

logger = logging.getLogger(__name__)

SEND_URL = "https://api.telegram.org/bot{token}/sendMessage"
TIMEOUT_SECONDS = 5.0

STATUS_TEXTS = {
    "uz": {
        "confirmed": "Buyurtmangiz №{id} qabul qilindi va tayyorlanmoqda.",
        "shipped": "Buyurtmangiz №{id} yuborildi — yo'lda. Tez orada yetib boradi.",
        "delivered": "Buyurtmangiz №{id} yetkazildi. Xaridingiz uchun rahmat!",
        "cancelled": "Afsuski, buyurtmangiz №{id} bekor qilindi. Savollaringiz bo'lsa, yozing.",
    },
    "ru": {
        "confirmed": "Ваш заказ №{id} принят и готовится.",
        "shipped": "Ваш заказ №{id} отправлен и уже в пути.",
        "delivered": "Ваш заказ №{id} доставлен. Спасибо за покупку!",
        "cancelled": "К сожалению, ваш заказ №{id} отменён. Если есть вопросы, напишите.",
    },
}


def send_message(token: str, chat_id: int, text: str) -> bool:
    if not token:
        return False
    try:
        response = httpx.post(
            SEND_URL.format(token=token),
            json={"chat_id": chat_id, "text": text[:4000]},
            timeout=TIMEOUT_SECONDS,
        )
    except httpx.HTTPError as exc:
        logger.warning("Telegram xabari yuborilmadi: %s", exc.__class__.__name__)
        return False
    if response.status_code != 200:
        logger.warning("Telegram xabari yuborilmadi: HTTP %s", response.status_code)
        return False
    return True


def status_text(order, new_status: str) -> str | None:
    lang = order.customer.language if order.customer and order.customer.language in STATUS_TEXTS else "uz"
    template = STATUS_TEXTS[lang].get(new_status)
    return template.format(id=order.pk) if template else None


def notify_customer_status(order, new_status: str) -> bool | None:
    """True/False: yuborildi/yuborilmadi. None: yuborish kerak emas (mijoz yo'q, holat uchun matn yo'q, token yo'q)."""
    if order.customer is None:
        return None
    text = status_text(order, new_status)
    token = order.shop.effective_token
    if not text or not token:
        return None
    return send_message(token, order.customer.telegram_id, text)
