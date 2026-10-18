"""Oddiy kesh asosidagi cheklovlar: kirishda qo'pol kuch hujumi va ommaviy ro'yxatdan o'tishga qarshi.

Eslatma: Django kesh sukut bo'yicha jarayon ichida (LocMem). Bir nechta jarayon/server
bo'lsa, umumiy kesh (Redis/Memcached) sozlang, aks holda har jarayonning hisobi alohida bo'ladi.
"""
from django.conf import settings
from django.core.cache import cache


def client_ip(request) -> str:
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if forwarded:
            return forwarded.split(",")[0].strip()[:64]
    return request.META.get("REMOTE_ADDR", "")[:64]


def count(key: str) -> int:
    return cache.get(key, 0)


def hit(key: str, window_seconds: int) -> int:
    cache.add(key, 0, window_seconds)
    try:
        return cache.incr(key)
    except ValueError:  # kalit shu orada tugab qoldi
        cache.set(key, 1, window_seconds)
        return 1


def reset(key: str) -> None:
    cache.delete(key)
