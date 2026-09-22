"""
collect_signals.py — соединяет matcher.py и backtest.py в одну команду.

Задача: превратить "нашёл пару, увидел edge на экране" в честную проверку.
Для каждой найденной пары Polymarket/Kalshi логируем сигнал ДО исхода
(backtest.log_signal), а дальше backtest.py сам скажет, была ли ценность
реальной. Один market_id логируется только один раз — иначе один и тот же
рынок попадёт в статистику много раз подряд (пока открыт) и исказит и
калибровку, и Brier повторным учётом одного и того же исхода.

Рынки в SOURCES — месячные "лестницы" (закрываются раз в месяц), это
осознанный выбор для старта: именно на них мы проверили весь пайплайн
end-to-end (даты+страйк совпадают корректно). Значит новых сигналов будет
мало — по ~5-6 в месяц на инструмент, не в час. Это честно про саму природу
подхода, а не баг сборщика: см. README "Малое n (<100) не значит ничего".
"""

import csv
import os

import backtest
from matcher import find_candidates, cross_edge, get_kalshi_markets
from scanner import search_polymarket_markets

# (ключевое слово для Polymarket, series_ticker Kalshi) — проверено вручную,
# оба возвращают рынки "above $X by month-end" с рабочими котировками.
SOURCES = [
    ("bitcoin", "KXBTCMAXMON"),
    ("ethereum", "KXETHMAXMON"),
]

MIN_SIM = 0.3
MAX_DATE_DIFF_HOURS = 6.0


def already_logged_ids() -> set:
    if not os.path.exists(backtest.LOG):
        return set()
    return {r["market_id"] for r in csv.DictReader(open(backtest.LOG, newline=""))}


def collect():
    logged = already_logged_ids()
    new_signals = 0

    for query, series_ticker in SOURCES:
        try:
            pm = search_polymarket_markets(query)
        except Exception as e:
            print(f"skip '{query}': polymarket error: {e}")
            continue
        pm = [m for m in pm if 0 < m["yes"] < 1]   # без уже вырожденных 0/1 цен

        try:
            kal = get_kalshi_markets(series_ticker=series_ticker, limit=100)
        except Exception as e:
            print(f"skip '{series_ticker}': kalshi error: {e}")
            continue

        pairs = find_candidates(pm, kal, min_sim=MIN_SIM, max_date_diff_hours=MAX_DATE_DIFF_HOURS)
        for p, k, score, diff in pairs:
            if p["id"] in logged:
                continue
            ce = cross_edge(p, k)
            backtest.log_signal(
                market_id=p["id"],
                question=p["question"],
                market_price=p["yes"],
                fair_prob=ce["fair_yes"],
                edge_val=ce["val_edge_pm"],
                venue=f"PM_vs_{series_ticker}",
            )
            logged.add(p["id"])
            new_signals += 1
            print(f"logged: {p['question'][:55]} "
                  f"(price={p['yes']:.3f} fair={ce['fair_yes']:.3f} edge={ce['val_edge_pm']*100:+.1f}%)")

    print(f"\nНовых сигналов: {new_signals}")


if __name__ == "__main__":
    backtest.update_resolutions()
    collect()
