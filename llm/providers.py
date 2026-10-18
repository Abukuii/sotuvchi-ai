"""LLM provayderlari. Hammasi bitta interfeys: LLMProvider.generate()."""
import httpx
from django.conf import settings

from .base import LLMError, LLMProvider, LLMRequest


def _post_json(url: str, *, headers: dict, payload: dict) -> dict:
    try:
        response = httpx.post(url, headers=headers, json=payload, timeout=settings.LLM_TIMEOUT)
    except httpx.TimeoutException as exc:
        raise LLMError("LLM javob berish vaqti tugadi") from exc
    except httpx.HTTPError as exc:
        raise LLMError(f"LLM bilan aloqa xatosi: {exc.__class__.__name__}") from exc
    if response.status_code == 429:
        raise LLMError("LLM limiti tugadi (429)")
    if response.status_code >= 400:
        # Javob matnini loglarga to'liq chiqarmaymiz: kalit yoki shaxsiy ma'lumot bo'lishi mumkin
        raise LLMError(f"LLM xatosi: HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise LLMError("LLM noto'g'ri javob qaytardi") from exc


class GeminiProvider(LLMProvider):
    name = "gemini"

    def generate(self, request: LLMRequest) -> str:
        if not settings.GEMINI_API_KEY:
            raise LLMError("GEMINI_API_KEY o'rnatilmagan")
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.GEMINI_MODEL}:generateContent"
        contents = [
            {"role": "user" if m["role"] == "user" else "model", "parts": [{"text": m["content"]}]}
            for m in request.messages
        ]
        payload = {
            "systemInstruction": {"parts": [{"text": request.system}]},
            "contents": contents,
            "generationConfig": {"temperature": 0.3, "responseMimeType": "application/json"},
        }
        data = _post_json(url, headers={"x-goog-api-key": settings.GEMINI_API_KEY}, payload=payload)
        try:
            return data["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Gemini bo'sh javob qaytardi") from exc


class GroqProvider(LLMProvider):
    name = "groq"

    def generate(self, request: LLMRequest) -> str:
        if not settings.GROQ_API_KEY:
            raise LLMError("GROQ_API_KEY o'rnatilmagan")
        payload = {
            "model": settings.GROQ_MODEL,
            "messages": [{"role": "system", "content": request.system}, *request.messages],
            "temperature": 0.3,
            "response_format": {"type": "json_object"},
        }
        data = _post_json(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
            payload=payload,
        )
        try:
            return data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Groq bo'sh javob qaytardi") from exc


class OllamaProvider(LLMProvider):
    name = "ollama"

    def generate(self, request: LLMRequest) -> str:
        payload = {
            "model": settings.OLLAMA_MODEL,
            "messages": [{"role": "system", "content": request.system}, *request.messages],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.3},
        }
        data = _post_json(f"{settings.OLLAMA_URL.rstrip('/')}/api/chat", headers={}, payload=payload)
        try:
            return data["message"]["content"]
        except (KeyError, TypeError) as exc:
            raise LLMError("Ollama bo'sh javob qaytardi") from exc
