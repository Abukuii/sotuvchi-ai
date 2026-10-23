"""Lokatsiya (koordinata) bilan ishlash: tekshirish, manzil matniga o'girish, xarita havolalari.

Teskari geokodlash (koordinata → manzil) ixtiyoriy va bepul: OpenStreetMap Nominatim. Faqat mijoz
lokatsiya yuborganda, bitta so'rov, qisqa kutish bilan. Xato/o'chirilgan bo'lsa manzil koordinata matni bo'ladi.
GEOCODER_ENABLED=0 bilan butunlay o'chiriladi (hech narsa tashqariga yuborilmaydi).
"""
import logging
import math

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)

NOMINATIM_URL = "https://nominatim.openstreetmap.org/reverse"
USER_AGENT = "SotuvchiAI/1.0 (Telegram shop assistant)"


def valid_coords(lat, lon) -> bool:
    try:
        lat, lon = float(lat), float(lon)
    except (TypeError, ValueError):
        return False
    return math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90 and -180 <= lon <= 180 and not (lat == 0 and lon == 0)


def coords_text(lat: float, lon: float) -> str:
    return f"📍 {lat:.5f}, {lon:.5f}"


def reverse_geocode(lat: float, lon: float, lang: str = "uz") -> str:
    """Manzil matni yoki "" (xato, o'chirilgan, natija yo'q)."""
    if not getattr(settings, "GEOCODER_ENABLED", True):
        return ""
    try:
        response = httpx.get(
            NOMINATIM_URL,
            params={"lat": f"{lat:.6f}", "lon": f"{lon:.6f}", "format": "jsonv2", "zoom": 18, "accept-language": "ru" if lang == "ru" else "uz,ru"},
            headers={"User-Agent": USER_AGENT},
            timeout=4.0,
        )
        if response.status_code != 200:
            return ""
        name = str(response.json().get("display_name") or "").strip()
    except (httpx.HTTPError, ValueError) as exc:
        logger.info("Geokodlash ishlamadi: %s", exc.__class__.__name__)
        return ""
    return name[:240]


def address_from_location(lat: float, lon: float, lang: str = "uz") -> str:
    """Buyurtma manzili: topilgan manzil + koordinata (mijoz aniq joyni ko'rishi uchun)."""
    found = reverse_geocode(lat, lon, lang)
    return f"{found} ({coords_text(lat, lon)})"[:300] if found else coords_text(lat, lon)


def map_url(lat: float, lon: float) -> str:
    return f"https://www.openstreetmap.org/?mlat={lat:.6f}&mlon={lon:.6f}#map=17/{lat:.6f}/{lon:.6f}"


def google_map_url(lat: float, lon: float) -> str:
    return f"https://maps.google.com/?q={lat:.6f},{lon:.6f}"
