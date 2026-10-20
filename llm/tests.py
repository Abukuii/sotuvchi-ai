"""LLM provayderlarini soxta HTTP javoblari bilan sinash (tashqi tarmoq kerak emas)."""
import json
from unittest import mock

import httpx
from django.test import SimpleTestCase, override_settings

from . import LLMError, LLMRequest, get_provider
from .providers import GeminiProvider, GroqProvider, OllamaProvider

SECRET = "SUPER-SECRET-API-KEY-123"


def response(status=200, body=None, text=None):
    request = httpx.Request("POST", "https://example.invalid/")
    if text is not None:
        return httpx.Response(status, text=text, request=request)
    return httpx.Response(status, json=body if body is not None else {}, request=request)


def make_request():
    return LLMRequest(
        system="SYSTEM PROMPT",
        messages=[
            {"role": "user", "content": "Salom"},
            {"role": "assistant", "content": "Assalomu alaykum"},
            {"role": "user", "content": "Narxi?"},
        ],
    )


@override_settings(GEMINI_API_KEY=SECRET, GEMINI_MODEL="gemini-test")
class GeminiTests(SimpleTestCase):
    def test_request_shape_and_parsing(self):
        ok = response(body={"candidates": [{"content": {"parts": [{"text": '{"reply": "x"}'}]}}]})
        with mock.patch("llm.providers.httpx.post", return_value=ok) as post:
            result = GeminiProvider().generate(make_request())
        self.assertEqual(result, '{"reply": "x"}')
        args, kwargs = post.call_args
        self.assertIn("gemini-test:generateContent", args[0])
        self.assertNotIn(SECRET, args[0])  # kalit URL da emas (loglarga tushmasin)
        self.assertEqual(kwargs["headers"], {"x-goog-api-key": SECRET})
        payload = kwargs["json"]
        self.assertEqual(payload["systemInstruction"]["parts"][0]["text"], "SYSTEM PROMPT")
        self.assertEqual([c["role"] for c in payload["contents"]], ["user", "model", "user"])
        self.assertEqual(payload["generationConfig"]["responseMimeType"], "application/json")

    def test_errors(self):
        cases = [
            (response(429), "limiti"),
            (response(500, text=f"boom {SECRET}"), "HTTP 500"),
            (response(200, text="not json"), "noto'g'ri"),
            (response(200, body={"candidates": []}), "bo'sh"),
            (response(200, body={}), "bo'sh"),
        ]
        for resp, expected in cases:
            with mock.patch("llm.providers.httpx.post", return_value=resp):
                with self.assertRaises(LLMError) as ctx:
                    GeminiProvider().generate(make_request())
            self.assertIn(expected, str(ctx.exception))
            self.assertNotIn(SECRET, str(ctx.exception))  # xato matnida kalit/javob matni yo'q

    def test_timeout_and_network_errors(self):
        for exc in (httpx.ReadTimeout("t"), httpx.ConnectError("c")):
            with mock.patch("llm.providers.httpx.post", side_effect=exc):
                with self.assertRaises(LLMError):
                    GeminiProvider().generate(make_request())

    @override_settings(GEMINI_API_KEY="")
    def test_missing_key(self):
        with self.assertRaises(LLMError) as ctx:
            GeminiProvider().generate(make_request())
        self.assertIn("GEMINI_API_KEY", str(ctx.exception))


@override_settings(GROQ_API_KEY=SECRET, GROQ_MODEL="groq-test")
class GroqTests(SimpleTestCase):
    def test_request_shape_and_parsing(self):
        ok = response(body={"choices": [{"message": {"content": '{"reply": "y"}'}}]})
        with mock.patch("llm.providers.httpx.post", return_value=ok) as post:
            result = GroqProvider().generate(make_request())
        self.assertEqual(result, '{"reply": "y"}')
        args, kwargs = post.call_args
        self.assertTrue(args[0].endswith("/chat/completions"))
        self.assertEqual(kwargs["headers"], {"Authorization": f"Bearer {SECRET}"})
        payload = kwargs["json"]
        self.assertEqual(payload["model"], "groq-test")
        self.assertEqual(payload["messages"][0], {"role": "system", "content": "SYSTEM PROMPT"})
        self.assertEqual(len(payload["messages"]), 4)
        self.assertEqual(payload["response_format"], {"type": "json_object"})

    def test_errors_do_not_leak(self):
        for resp in (response(429), response(401, text=SECRET), response(200, body={"choices": []})):
            with mock.patch("llm.providers.httpx.post", return_value=resp):
                with self.assertRaises(LLMError) as ctx:
                    GroqProvider().generate(make_request())
            self.assertNotIn(SECRET, str(ctx.exception))

    @override_settings(GROQ_API_KEY="")
    def test_missing_key(self):
        with self.assertRaises(LLMError):
            GroqProvider().generate(make_request())


@override_settings(OLLAMA_URL="http://localhost:11434/", OLLAMA_MODEL="llama-test")
class OllamaTests(SimpleTestCase):
    def test_request_shape_and_parsing(self):
        ok = response(body={"message": {"content": '{"reply": "z"}'}})
        with mock.patch("llm.providers.httpx.post", return_value=ok) as post:
            result = OllamaProvider().generate(make_request())
        self.assertEqual(result, '{"reply": "z"}')
        args, kwargs = post.call_args
        self.assertEqual(args[0], "http://localhost:11434/api/chat")
        payload = kwargs["json"]
        self.assertEqual((payload["model"], payload["stream"], payload["format"]), ("llama-test", False, "json"))

    def test_connection_refused_is_llm_error(self):
        with mock.patch("llm.providers.httpx.post", side_effect=httpx.ConnectError("refused")):
            with self.assertRaises(LLMError):
                OllamaProvider().generate(make_request())

    def test_bad_body(self):
        with mock.patch("llm.providers.httpx.post", return_value=response(body={"x": 1})):
            with self.assertRaises(LLMError):
                OllamaProvider().generate(make_request())


class RegistryTests(SimpleTestCase):
    def test_known_and_unknown(self):
        for name in ("gemini", "groq", "ollama", "mock", "GEMINI"):
            self.assertTrue(get_provider(name).name in {"gemini", "groq", "ollama", "mock"})
        with self.assertRaises(LLMError):
            get_provider("gpt-nothing")

    @override_settings(LLM_PROVIDER="mock")
    def test_default_from_settings(self):
        self.assertEqual(get_provider().name, "mock")

    def test_mock_returns_valid_json_for_unknown(self):
        out = json.loads(get_provider("mock").generate(LLMRequest(system="", messages=[], meta={"language": "uz", "last_user": "???", "hits": [], "draft": {}})))
        self.assertEqual(out["intent"], "handoff")
