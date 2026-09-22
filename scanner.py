"""
scanner.py — тянет активные рынки с публичного API Polymarket (Gamma).

Отдаёт список бинарных (YES/NO) рынков в едином формате, который дальше
используют matcher.py и backtest.py. Только чтение публичных данных.
"""

import json
import requests

GAMMA = "https://gamma-api.polymarket.com/markets"
SEARCH = "https://gamma-api.polymarket.com/public-search"


def _to_market(m: dict) -> dict | None:
    """Общая нормализация сырого объекта рынка Gamma в {id, question, yes, no, end_date}."""
    raw = m.get("outcomePrices")
    if not raw:
        return None
    try:
        prices = [float(p) for p in json.loads(raw)]
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    if len(prices) != 2:                # берём только бинарные рынки
        return None
    return {
        "id": m.get("id"),
        "question": m.get("question", "").strip(),
        "yes": prices[0],
        "no": prices[1],
        "end_date": m.get("endDate"),    # ISO 8601, напр. "2027-01-01T04:59:00Z"
    }


def get_polymarket_markets(limit: int = 200) -> list[dict]:
    """
    Вернуть активные бинарные рынки Polymarket, отсортированные по объёму.

    Формат каждого элемента: см. _to_market(). Топ по объёму — обычно
    политика/спорт/поп-культура текущего момента; узкие/новые темы (напр.
    отдельные крипто-«лестницы») сюда часто не попадают — для них см.
    search_polymarket_markets().
    """
    params = {
        "closed": "false",
        "limit": limit,
        "order": "volume",
        "ascending": "false",
    }
    resp = requests.get(GAMMA, params=params, timeout=15)
    resp.raise_for_status()
    return [mk for m in resp.json() if (mk := _to_market(m))]


def search_polymarket_markets(query: str, limit_per_type: int = 20) -> list[dict]:
    """
    Найти рынки по ключевому слову через public-search (а не по объёму) —
    так находятся нишевые темы вроде конкретной крипто-«лестницы», которые
    не попадают в топ-200 по объёму. Возвращает объединённые рынки всех
    найденных событий, в том же формате, что get_polymarket_markets().
    """
    resp = requests.get(SEARCH, params={"q": query, "limit_per_type": limit_per_type}, timeout=15)
    resp.raise_for_status()
    out = []
    for event in resp.json().get("events", []):
        for m in event.get("markets", []):
            mk = _to_market(m)
            if mk:
                out.append(mk)
    return out


if __name__ == "__main__":
    markets = get_polymarket_markets(limit=50)
    print(f"Получено бинарных рынков (топ по объёму): {len(markets)}\n")
    for m in markets[:15]:
        print(f"  {m['question'][:60]:60} YES={m['yes']:.2f} NO={m['no']:.2f}")
