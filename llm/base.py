from abc import ABC, abstractmethod
from dataclasses import dataclass, field


class LLMError(Exception):
    """LLM provayderi javob bera olmadi (tarmoq, limit, noto'g'ri kalit va h.k.)."""


@dataclass
class LLMRequest:
    system: str
    # [{"role": "user" | "assistant", "content": "..."}]
    messages: list[dict]
    # Faqat "mock" provayder uchun: katalog natijalari, joriy buyurtma qoralamasi, til.
    # Haqiqiy provayderlar buni ishlatmaydi (ma'lumot allaqachon system promptda).
    meta: dict = field(default_factory=dict)


class LLMProvider(ABC):
    name = "base"

    @abstractmethod
    def generate(self, request: LLMRequest) -> str:
        """JSON matn qaytaradi (yoki LLMError ko'taradi)."""
