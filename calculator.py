"""
calculator.py — ядро всех расчётов.

Здесь живёт вся математика ценности ставки (+EV):
де-виг (убираем маржу), edge после комиссии, критерий Келли.
Всё остальное в проекте — это "водопровод" вокруг этих функций.

Ничего не тянет из сети, ничего не ставит. Чистые функции — их удобно
проверять и переиспользовать.
"""

from dataclasses import dataclass


@dataclass
class Verdict:
    fair_prob: float      # справедливая вероятность исхода (0..1)
    fair_price: float     # справедливая цена контракта в центах
    gross_edge: float     # перевес до комиссии (доля, напр. 0.05 = +5%)
    net_edge: float       # перевес после комиссии
    kelly_full: float     # полный Келли (доля банка)
    label: str            # "value" | "thin" | "skip"


def devig_two_way(odds_a: float, odds_b: float) -> float:
    """
    Убрать маржу букмекера и вернуть справедливую вероятность исхода A.

    Простой (пропорциональный) метод: делим сырую вероятность на сумму.
    Он немного завышает вероятность фаворитов — для учёбы годится,
    для продакшена берут метод Shin или логарифмический.
    """
    if not (odds_a > 1 and odds_b > 1):
        raise ValueError("Коэффициенты должны быть > 1")
    raw_a, raw_b = 1 / odds_a, 1 / odds_b
    return raw_a / (raw_a + raw_b)


def edge(fair_prob: float, market_price: float, fee_pct: float = 2.0) -> dict:
    """
    Посчитать перевес при покупке YES по цене market_price (в долларах, 0..1).

    fair_prob    — наша оценка справедливой вероятности (эталон).
    market_price — во сколько обходится контракт на рынке.
    fee_pct      — комиссия с выплаты $1 (упрощённо; на Polymarket она
                   зависит от категории и максимальна у цены 50c).
    """
    if not (0 < market_price < 1):
        raise ValueError("Цена должна быть в диапазоне 0..1")
    payout = 1 - fee_pct / 100                 # выплата на выигрышный контракт
    gross_ev = fair_prob * 1 - market_price
    net_ev = fair_prob * payout - market_price
    return {
        "gross_edge": gross_ev / market_price,
        "net_edge": net_ev / market_price,
        "payout": payout,
    }


def kelly_fraction(fair_prob: float, market_price: float, fee_pct: float = 2.0) -> float:
    """
    Полный критерий Келли для покупки контракта.

    Ставка = market_price; на выигрыше получаем payout, на проигрыше теряем ставку.
    Возвращает долю банка (может быть <= 0 — тогда ставки нет).
    """
    payout = 1 - fee_pct / 100
    b = (payout - market_price) / market_price   # чистый выигрыш на единицу ставки
    if b <= 0:
        return 0.0
    p = fair_prob
    f = (b * p - (1 - p)) / b
    return max(0.0, f)


def analyse(odds_a: float, odds_b: float, market_price: float,
            fee_pct: float = 2.0, thin_threshold: float = 0.025) -> Verdict:
    """
    Полный разбор одной ставки: эталон из линии БК (odds_a/odds_b),
    цена — с рынка предсказаний. Возвращает Verdict с вердиктом.
    """
    fair_prob = devig_two_way(odds_a, odds_b)
    e = edge(fair_prob, market_price, fee_pct)
    k = kelly_fraction(fair_prob, market_price, fee_pct)

    if e["net_edge"] <= 0:
        label = "skip"          # перевес не бьёт комиссию
    elif e["net_edge"] < thin_threshold:
        label = "thin"          # есть, но проскальзывание/запаздывание съедят
    else:
        label = "value"

    return Verdict(
        fair_prob=fair_prob,
        fair_price=fair_prob * 100,
        gross_edge=e["gross_edge"],
        net_edge=e["net_edge"],
        kelly_full=k,
        label=label,
    )


if __name__ == "__main__":
    # Тот самый пример из обсуждения: 1.75 / 2.20, цена 50c, комиссия 2%.
    v = analyse(1.75, 2.20, 0.50, fee_pct=2.0)
    print(f"Справедливая вероятность: {v.fair_prob*100:.1f}%")
    print(f"Справедливая цена:        {v.fair_price:.1f}c")
    print(f"Перевес до комиссии:      {v.gross_edge*100:+.1f}%")
    print(f"Перевес после комиссии:   {v.net_edge*100:+.1f}%")
    print(f"Полный Келли:             {v.kelly_full*100:.1f}% банка")
    print(f"Вердикт:                  {v.label.upper()}")
