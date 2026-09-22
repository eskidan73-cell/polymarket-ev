"""
backtest.py — самый важный файл. Отвечает на единственный честный вопрос:
"мой сканер находит реальную ценность или красиво подсвеченный шум?"

Логика: сохраняем сигнал ДО исхода, потом сверяем с тем, чем рынок реально
закрылся. Если сканер говорил "справедливо 60%", то на серии таких сигналов
YES должен сбываться примерно в 60% случаев. Иначе эталон врёт, а "edge" — миф.

Три проверки:
  (A) калибровка   — сбывается ли предсказанная вероятность
  (B) деньги       — средний P&L на ставку $1
  (C) Brier vs рынок — а точнее ли ты, чем сама цена, которую хотел обыграть
"""

import csv
import json
import os
from datetime import datetime, timezone

import requests

LOG = "signals.csv"
FIELDS = ["ts", "market_id", "question", "venue",
          "market_price", "fair_prob", "edge", "resolved", "outcome"]


# ------------------------------------------------------------------ #
# Шаг 1. Логируем сигнал (до исхода). Значения потом НЕ трогаем.
# ------------------------------------------------------------------ #
def log_signal(market_id, question, market_price, fair_prob, edge_val, venue):
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "market_id": market_id,
        "question": question[:80],
        "venue": venue,
        "market_price": round(market_price, 4),
        "fair_prob": round(fair_prob, 4),
        "edge": round(edge_val, 4),
        "resolved": "",
        "outcome": "",
    }
    exists = os.path.exists(LOG)
    with open(LOG, "a", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        if not exists:
            w.writeheader()
        w.writerow(row)


# ------------------------------------------------------------------ #
# Шаг 2. Дописываем исход после закрытия рынка.
# ------------------------------------------------------------------ #
def fetch_resolution(market_id):
    """1 если YES сбылся, 0 если нет, None если рынок ещё открыт.
       Поля зависят от площадки — здесь пример для Polymarket."""
    url = f"https://gamma-api.polymarket.com/markets/{market_id}"
    m = requests.get(url, timeout=15).json()
    if not m.get("closed"):
        return None
    try:
        prices = [float(p) for p in json.loads(m.get("outcomePrices", "[]"))]
    except (json.JSONDecodeError, ValueError, TypeError):
        return None
    return 1 if prices and prices[0] > 0.5 else 0


def update_resolutions():
    if not os.path.exists(LOG):
        print("Файла сигналов ещё нет."); return
    rows = list(csv.DictReader(open(LOG)))
    updated = 0
    for r in rows:
        if r["outcome"] == "":
            try:
                res = fetch_resolution(r["market_id"])
            except Exception:
                res = None
            if res is not None:
                r["resolved"], r["outcome"] = "yes", str(res)
                updated += 1
    with open(LOG, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader(); w.writerows(rows)
    print(f"Дописано исходов: {updated}")


# ------------------------------------------------------------------ #
# Шаг 3. Три проверки правды.
# ------------------------------------------------------------------ #
def evaluate():
    if not os.path.exists(LOG):
        print("Нет данных."); return
    rows = [r for r in csv.DictReader(open(LOG)) if r["outcome"] in ("0", "1")]
    n = len(rows)
    if n == 0:
        print("Нет разрешённых сигналов — сначала дождись закрытия рынков."); return

    # (A) КАЛИБРОВКА
    buckets = {}
    for r in rows:
        b = round(float(r["fair_prob"]) * 10) / 10
        buckets.setdefault(b, []).append(int(r["outcome"]))
    print("Калибровка (предсказано -> фактически сбылось):")
    for b in sorted(buckets):
        hits, tot = sum(buckets[b]), len(buckets[b])
        print(f"  {b*100:>3.0f}%  ->  {hits/tot*100:>5.1f}%   (n={tot})")

    # (B) ДЕНЬГИ
    pnl = 0.0
    for r in rows:
        cost, won = float(r["market_price"]), int(r["outcome"])
        pnl += (1.0 - cost) if won else (-cost)
    print(f"\nСигналов разрешено: {n}")
    print(f"Средний P&L на ставку $1: {pnl/n:+.4f}  (всего {pnl:+.2f})")
    if n < 100:
        print("  ⚠ n < 100 — статистически это почти ничего. Не делай выводов.")

    # (C) BRIER vs РЫНОК
    brier = sum((float(r["fair_prob"]) - int(r["outcome"]))**2 for r in rows) / n
    brier_mkt = sum((float(r["market_price"]) - int(r["outcome"]))**2 for r in rows) / n
    print(f"\nBrier сканера: {brier:.4f}   Brier рынка: {brier_mkt:.4f}")
    print("Ниже = точнее. Если у рынка не хуже — твой эталон не даёт преимущества,")
    print("и 'edge' на экране был шумом, а не ценностью.")


if __name__ == "__main__":
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else "eval"
    if cmd == "update":
        update_resolutions()
    elif cmd == "demo":
        # записать пару демо-сигналов, чтобы увидеть формат файла
        log_signal("demo1", "Demo market A", 0.50, 0.557, 0.092, "PM")
        log_signal("demo2", "Demo market B", 0.30, 0.28, -0.05, "PM")
        print(f"Записаны демо-сигналы в {LOG}")
    else:
        evaluate()
