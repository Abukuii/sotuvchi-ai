"""Katalogdan mahsulot qidirish (RAG ning "retrieval" qismi).

Kichik va o'rta do'konlar (<= ~2000 mahsulot) uchun tashqi vektor bazasiz,
tezkor va tushunarli leksik qidiruv. Katta hajm uchun pgvector/embedding
qo'shish "keyingi qadam" sifatida README da yozilgan.
"""
from dataclasses import dataclass

from .models import Product
from .text import keywords, tokenize


@dataclass
class Hit:
    product: Product
    score: float


def _token_score(query_token: str, product_token: str) -> float:
    if query_token == product_token:
        return 3.0
    if query_token.isdigit() or product_token.isdigit():
        return 0.0
    common = 0
    for a, b in zip(query_token, product_token):
        if a != b:
            break
        common += 1
    shortest = min(len(query_token), len(product_token))
    # Qo'shimchalar (-lar, -ni, -ning, -ы, -ов) farqini kechiradi
    if common >= 4 and common >= shortest - 2:
        return 2.0
    return 0.0


def score_product(query_tokens: list[str], product: Product) -> float:
    name_tokens = tokenize(product.name)
    meta_tokens = tokenize(f"{product.category} {product.sku} {product.description}")
    total = 0.0
    for qt in query_tokens:
        best_name = max((_token_score(qt, pt) for pt in name_tokens), default=0.0)
        best_meta = max((_token_score(qt, pt) for pt in meta_tokens), default=0.0)
        total += max(best_name * 2.0, best_meta)
    return total


def search_products(shop, query: str, limit: int = 5) -> list[Hit]:
    query_tokens = keywords(query)
    if not query_tokens:
        return []
    hits: list[Hit] = []
    for product in Product.objects.filter(shop=shop, is_active=True):
        score = score_product(query_tokens, product)
        if score > 0:
            hits.append(Hit(product=product, score=score))
    hits.sort(key=lambda h: (-h.score, h.product.name))
    return hits[:limit]
