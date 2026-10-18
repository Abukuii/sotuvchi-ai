"""Sotuvchi AI - Django sozlamalari.

Barcha maxfiy qiymatlar .env faylidan (yoki muhit o'zgaruvchilaridan) o'qiladi.
"""
import os
from pathlib import Path
from urllib.parse import unquote, urlparse

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


DEBUG = env_bool("DJANGO_DEBUG", False)

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
_PLACEHOLDER_KEYS = {"", "change-me-to-a-long-random-string", "dev-only-insecure-key-do-not-use-in-production"}
if SECRET_KEY in _PLACEHOLDER_KEYS or len(SECRET_KEY) < 32:
    if DEBUG:
        SECRET_KEY = SECRET_KEY if len(SECRET_KEY) >= 32 else "dev-only-insecure-key-do-not-use-in-production"
    else:
        raise RuntimeError(
            "DJANGO_SECRET_KEY o'rnatilmagan yoki namuna qiymatida. "
            "Yangi kalit: python -c \"import secrets; print(secrets.token_urlsafe(50))\""
        )

# Bot tokenlarini bazada shifrlash kaliti. Bo'sh bo'lsa SECRET_KEY dan hosil qilinadi.
# Diqqat: bu kalit yo'qolsa yoki o'zgarsa, saqlangan tokenlarni qayta kiritish kerak bo'ladi.
TOKEN_ENCRYPTION_KEY = os.environ.get("TOKEN_ENCRYPTION_KEY", "")

ALLOWED_HOSTS = [h.strip() for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "127.0.0.1,localhost").split(",") if h.strip()]

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "shops",
    "catalog",
    "conversations",
    "orders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


def _database_from_url(url: str) -> dict:
    parsed = urlparse(url)
    if parsed.scheme not in {"postgres", "postgresql"}:
        raise RuntimeError("DATABASE_URL faqat postgres:// formatini qo'llab-quvvatlaydi.")
    return {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": parsed.path.lstrip("/"),
        "USER": unquote(parsed.username or ""),
        "PASSWORD": unquote(parsed.password or ""),
        "HOST": parsed.hostname or "localhost",
        "PORT": str(parsed.port or 5432),
    }


_db_url = os.environ.get("DATABASE_URL", "").strip()
if _db_url:
    DATABASES = {"default": _database_from_url(_db_url)}
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 8}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "uz"
TIME_ZONE = "Asia/Tashkent"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "dashboard"
LOGOUT_REDIRECT_URL = "login"

# Xavfsizlik: faqat HTTPS orqali ishlaganda yoqiladi (DEBUG=0 bo'lsa).
if not DEBUG:
    SESSION_COOKIE_SECURE = env_bool("DJANGO_SECURE_COOKIES", True)
    CSRF_COOKIE_SECURE = SESSION_COOKIE_SECURE
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"
SECURE_REFERRER_POLICY = "same-origin"

# Ixtiyoriy (sukut bo'yicha o'chiq): HTTPS orqasida ishlatish uchun
if env_bool("DJANGO_BEHIND_PROXY", False):
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
if env_bool("DJANGO_FORCE_HTTPS", False):
    SECURE_SSL_REDIRECT = True
    SECURE_HSTS_SECONDS = 31536000
CSRF_TRUSTED_ORIGINS = [o.strip() for o in os.environ.get("DJANGO_CSRF_TRUSTED_ORIGINS", "").split(",") if o.strip()]

# Yuklanadigan Excel fayl chegaralari
MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB
MAX_XLSX_UNCOMPRESSED_BYTES = 30 * 1024 * 1024  # zip-bomba himoyasi
MAX_CATALOG_ROWS = 2000
MAX_PRICE = 10**11  # so'm
MAX_STOCK = 10**7
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_BYTES

# Kirish va ro'yxatdan o'tishni qo'pol kuch (brute-force) hujumidan himoya
LOGIN_MAX_ATTEMPTS = 5  # bitta IP + username uchun
LOGIN_IP_MAX_ATTEMPTS = 30  # bitta IP uchun
LOGIN_LOCK_SECONDS = 15 * 60
SIGNUP_MAX_PER_HOUR = 10  # bitta IP dan
# Faqat ishonchli reverse-proxy orqasida yoqing, aks holda IP soxtalashtirilishi mumkin
TRUST_X_FORWARDED_FOR = env_bool("DJANGO_TRUST_X_FORWARDED_FOR", False)

# --- LLM ---
LLM_PROVIDER = os.environ.get("LLM_PROVIDER", "mock").strip().lower()
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "30"))
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.0-flash")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")
GROQ_MODEL = os.environ.get("GROQ_MODEL", "llama-3.3-70b-versatile")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "llama3.1")

# Suhbat tarixidan LLM ga yuboriladigan oxirgi xabarlar soni
CHAT_HISTORY_LIMIT = 8
# Bitta mijoz bir daqiqada yuborishi mumkin bo'lgan xabarlar soni (spamdan himoya)
RATE_LIMIT_PER_MINUTE = 12
# Mijoz xabarining maksimal uzunligi
MAX_MESSAGE_CHARS = 1000
