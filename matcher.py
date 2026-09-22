"""
matcher.py — сопоставляет рынки Polymarket и Kalshi и считает межплощадочный edge.

ВАЖНО (это 90% сложности и главный урок проекта):
матчинг по названию — только ЧЕРНОВОЙ фильтр-кандидат. Два рынка с похожим
вопросом могут по-разному определять критерии закрытия, источник истины и
дедлайн. Пока ты глазами не подтвердил, что правила совпадают, любая "вилка"
между ними — фантом. Именно поэтому серьёзные исследования ставят порог edge
высоким: тонкие расхождения съедаются тем, что рынки не идентичны.
"""

import re
import time
import requests
from datetime import datetime
from difflib import SequenceMatcher

KALSHI = "https://api.elections.kalshi.com/trade-api/v2/markets"


def _get_with_retries(url, params, tries: int = 3, timeout: int = 15):
    """GET с ретраями — публичные API площадок временами отдают таймаут/обрыв
    на ровном месте, особенно при частой пагинации. Не мешает при единичных
    запросах, спасает при переборе многих страниц подряд."""
    last_exc = None
    for attempt in range(tries):
        try:
            resp = requests.get(url, params=params, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            last_exc = e
            if attempt < tries - 1:
                time.sleep(1.5 * (attempt + 1))
    raise last_exc


def _parse_iso(s: str | None) -> datetime | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_kalshi_markets(series_ticker: str | None = None, limit: int = 200,
                        max_pages: int = 10, page_delay: float = 0.3) -> list[dict]:
    """
    Вернуть открытые рынки Kalshi в том же формате, что и scanner.py.

    Цены отдаём в *_dollars-полях (0..1 уже в долларах, без деления на 100).
    Базовый URL/поля меняются — уже менялись один раз с момента написания
    (были yes_ask/no_ask в центах) — сверяйся с актуальной докой Kalshi.

    ЧЕСТНОЕ ОГРАНИЧЕНИЕ (проверено на живых данных): без series_ticker
    (весь открытый листинг подряд) ~99.9% результата — автосгенерированные
    мультивариантные parlay/combo-рынки с нулевой или бессмысленной ценой
    (yes_ask+no_ask далеко от ~1). Из 8000 просмотренных так рынков нашлось
    всего 11 не-combo, и ни один не прошёл ценовой sanity-фильтр. Поднимать
    max_pages в этом режиме бесполезно — глубже там то же самое.

    РАБОЧИЙ ПУТЬ: указывай series_ticker конкретной серии (список серий —
    GET /series?category=<Crypto|Politics|...>). Например, у серии KXBTCD
    ("Bitcoin price above/below") рынок у страйка около текущей цены имеет
    нормальную двустороннюю котировку (проверено: yes=0.58/no=0.43 у страйка
    $85,400 при цене BTC ~$85,4хх). Комбо-рынки в конкретной серии почти не
    встречаются — там уже нет смысла резать по mve_collection_ticker.
    """
    out = []
    cursor = None
    for _ in range(max_pages):
        if len(out) >= limit:
            break
        params = {"status": "open", "limit": 200}
        if series_ticker:
            params["series_ticker"] = series_ticker
        if cursor:
            params["cursor"] = cursor
        resp = _get_with_retries(KALSHI, params)
        data = resp.json()

        for m in data.get("markets", []):
            if m.get("mve_collection_ticker"):
                continue  # автосгенерированный parlay/combo-рынок, не то, что мы ищем
            yes, no = m.get("yes_ask_dollars"), m.get("no_ask_dollars")
            if not (yes and no):
                continue
            yes, no = float(yes), float(no)
            if not (0 < yes < 1 and 0 < no < 1 and 0.9 <= yes + no <= 1.15):
                continue  # нет реальной двусторонней котировки — цена не значит ничего
            out.append({
                "id": m.get("ticker"),
                "question": (m.get("title") or "").strip(),
                "yes": yes,
                "no": no,
                "end_date": m.get("close_time"),   # ISO 8601
            })

        cursor = data.get("cursor")
        if not cursor or not data.get("markets"):
            break
        time.sleep(page_delay)   # не долбить API пачкой запросов подряд
    return out[:limit]


def get_kalshi_series(category: str, limit: int = 200) -> list[dict]:
    """Список серий Kalshi в категории (напр. 'Crypto', 'Politics') — {ticker, title}."""
    resp = _get_with_retries("https://api.elections.kalshi.com/trade-api/v2/series",
                              {"category": category, "limit": limit})
    return [{"ticker": s["ticker"], "title": s["title"]} for s in resp.json().get("series", [])]


def get_kalshi_markets_multi(series_tickers: list[str], **kwargs) -> list[dict]:
    """get_kalshi_markets по нескольким series_ticker сразу, объединённо."""
    out = []
    for t in series_tickers:
        out.extend(get_kalshi_markets(series_ticker=t, **kwargs))
    return out


def _norm(s: str) -> str:
    return "".join(c.lower() for c in s if c.isalnum() or c == " ")


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, _norm(a), _norm(b)).ratio()


_DOLLAR_RE = re.compile(r"\$([\d,]+(?:\.\d+)?)")


def extract_strike(text: str) -> float | None:
    """
    Единственная денежная сумма в тексте (типа "$92,500" или "$97500.00"),
    или None если сумм нет или их несколько (неоднозначно).

    ЗАЧЕМ ЭТО НУЖНО (найдено на живых данных, не гипотетически): у
    "лестничных" рынков ("Bitcoin reach $X in September" / "BTC above $X
    by...") почти весь текст — шаблон, меняется только число. SequenceMatcher
    сравнивает строку целиком, и на длинном шаблонном тексте разница в паре
    цифр тонет в общем сходстве — proверено, что $90,000 спокойно матчился
    с $97,500 вместо своего настоящего аналога, при живом наличии верного
    кандидата в списке. Для рынков с ценовым порогом сходство текста —
    ненадёжный сигнал, нужно сверять само число.
    """
    amounts = _DOLLAR_RE.findall(text)
    if len(amounts) != 1:
        return None
    return float(amounts[0].replace(",", ""))


def date_diff_hours(pm: dict, kal: dict) -> float | None:
    """
    Расхождение дедлайнов закрытия в часах, или None если у какой-то
    из сторон нет даты (тогда её нельзя ни подтвердить, ни отбросить —
    считай такую пару неподтверждённой).
    """
    a, b = _parse_iso(pm.get("end_date")), _parse_iso(kal.get("end_date"))
    if a is None or b is None:
        return None
    return abs((a - b).total_seconds()) / 3600


def find_candidates(pm: list[dict], kal: list[dict], min_sim: float = 0.6,
                     max_date_diff_hours: float | None = 6.0):
    """
    Черновые пары «похоже, одно и то же событие», отсортированы по схожести.
    Возвращает список (polymarket_market, kalshi_market, score, date_diff_hours).

    max_date_diff_hours — режет большую часть фантомных пар: если дедлайны
    закрытия расходятся сильнее (или дату не удалось разобрать хотя бы у
    одной площадки), пара отбрасывается. None отключает фильтр — но тогда
    сверяй пары глазами ещё внимательнее.

    Совпадение дат — необходимое условие, не достаточное: даже при
    одинаковом дедлайне источники истины и критерии закрытия могут
    различаться. ОБЯЗАТЕЛЬНО проверяй пары глазами перед любыми выводами.

    Ценовой порог ("$X") в вопросе — ОБЯЗАТЕЛЬНОЕ условие, если он есть
    ровно один и там, и там: на "лестничных" рынках (Bitcoin reach $X,
    BTC above $X) текст почти целиком шаблонный, и SequenceMatcher по
    всей строке ненадёжно различает соседние пороги — проверено на живых
    данных, что $90,000 матчился с $97,500 при живом наличии правильного
    кандидата в списке. Если у обеих сторон есть однозначная сумма и она
    не совпадает — кандидат для этого k не рассматривается вообще.
    """
    pairs = []
    for p in pm:
        p_strike = extract_strike(p["question"])
        best, score = None, 0.0
        for k in kal:
            if p_strike is not None:
                k_strike = extract_strike(k["question"])
                if k_strike is not None and k_strike != p_strike:
                    continue
            s = similarity(p["question"], k["question"])
            if s > score:
                best, score = k, s
        if not (best and score >= min_sim):
            continue
        diff = date_diff_hours(p, best)
        if max_date_diff_hours is not None and (diff is None or diff > max_date_diff_hours):
            continue
        pairs.append((p, best, score, diff))
    return sorted(pairs, key=lambda x: -x[2])


def cross_edge(pm: dict, kal: dict, fee: float = 0.02) -> dict:
    """
    Два РАЗНЫХ вопроса по одной паре — не путай их:

    (A) АРБИТРАЖ: купить YES там, где дешевле, и NO там, где дешевле.
        Если корзина < $1 — теоретически профит при любом исходе,
        НО только если оба рынка разрешатся идентично.

    (B) VALUE: считаем Kalshi эталоном (де-виг из самого Kalshi) и смотрим,
        не дёшев ли YES на Polymarket относительно этой оценки. Тут нет
        гарантии — только матожидание, и вера, что эталон точнее.
    """
    # (A) арбитраж
    best_yes = min(pm["yes"], kal["yes"])
    best_no = min(pm["no"], kal["no"])
    basket = best_yes + best_no
    arb_gross = 1 - basket
    arb_net = (1 - fee) - basket

    # (B) value: Kalshi как эталон, ставим на Polymarket
    fair_yes = kal["yes"] / (kal["yes"] + kal["no"])
    val_edge_pm = (fair_yes * (1 - fee) - pm["yes"]) / pm["yes"]

    return {
        "basket": basket,
        "arb_gross": arb_gross,
        "arb_net": arb_net,
        "fair_yes": fair_yes,
        "val_edge_pm": val_edge_pm,
    }


if __name__ == "__main__":
    from scanner import search_polymarket_markets

    # РАБОЧИЙ путь (проверено на живых данных 2026-09-22): ищем Polymarket
    # по ключевому слову, а Kalshi — по конкретной series_ticker, а не
    # перебором всего открытого листинга (тот на ~99.9% состоит из
    # автосгенерированных parlay-комбо, см. докстринг get_kalshi_markets).
    # Список серий по категории: get_kalshi_series("Crypto"/"Politics"/...).
    QUERY = "bitcoin"
    SERIES_TICKER = "KXBTCMAXMON"   # "BTC above $X by month-end" (trimmed mean)

    pm = search_polymarket_markets(QUERY, limit_per_type=20)
    pm = [m for m in pm if 0 < m["yes"] < 1]   # без уже вырожденных 0/1 цен
    kal = get_kalshi_markets(series_ticker=SERIES_TICKER, limit=100)
    print(f"Polymarket ('{QUERY}'): {len(pm)} рынков | "
          f"Kalshi ({SERIES_TICKER}): {len(kal)} рынков\n")

    pairs = find_candidates(pm, kal, min_sim=0.3, max_date_diff_hours=6.0)
    print(f"Пар-кандидатов: {len(pairs)} "
          f"(страйк и дата закрытия совпали — но критерии расчёта всё ещё "
          f"могут отличаться, напр. 'максимум за месяц' vs 'на конец месяца')\n")

    for p, k, score, diff in pairs[:10]:
        ce = cross_edge(p, k)
        print(f"[sim={score:.2f}, dt={diff:.1f}h] PM: {p['question'][:55]}")
        print(f"        KAL: {k['question'][:55]}")
        print(f"        arb_net={ce['arb_net']*100:+.1f}%  "
              f"value_on_PM={ce['val_edge_pm']*100:+.1f}%\n")
