import pytest

from calculator import devig_two_way, edge, kelly_fraction, analyse


# Эталонный пример из README/обсуждения: кэфы 1.75/2.20, цена 50c, комиссия 2%.
REF_ODDS_A, REF_ODDS_B = 1.75, 2.20
REF_PRICE, REF_FEE = 0.50, 2.0
REF_FAIR_PROB = 0.5569620253164557


def test_devig_two_way_reference():
    assert devig_two_way(REF_ODDS_A, REF_ODDS_B) == pytest.approx(REF_FAIR_PROB)


def test_devig_two_way_equal_odds_is_fifty_fifty():
    assert devig_two_way(2.0, 2.0) == pytest.approx(0.5)


@pytest.mark.parametrize("odds_a,odds_b", [(1.0, 2.0), (2.0, 1.0), (0.5, 2.0), (2.0, 0.9)])
def test_devig_two_way_rejects_odds_not_above_one(odds_a, odds_b):
    with pytest.raises(ValueError):
        devig_two_way(odds_a, odds_b)


def test_edge_reference_values():
    e = edge(REF_FAIR_PROB, REF_PRICE, fee_pct=REF_FEE)
    assert e["gross_edge"] == pytest.approx(0.11392405063291133)
    assert e["net_edge"] == pytest.approx(0.09164556962025316)
    assert e["payout"] == pytest.approx(0.98)


@pytest.mark.parametrize("price", [0.0, 1.0, -0.1, 1.5])
def test_edge_rejects_price_outside_open_unit_interval(price):
    with pytest.raises(ValueError):
        edge(0.5, price, fee_pct=REF_FEE)


def test_edge_fair_price_has_zero_edge():
    # По справедливой цене (с учётом комиссии) net edge должен быть ровно 0.
    fair_prob = 0.6
    fee_pct = 2.0
    payout = 1 - fee_pct / 100
    fair_price = fair_prob * payout
    e = edge(fair_prob, fair_price, fee_pct=fee_pct)
    assert e["net_edge"] == pytest.approx(0.0, abs=1e-9)


def test_kelly_fraction_reference():
    k = kelly_fraction(REF_FAIR_PROB, REF_PRICE, fee_pct=REF_FEE)
    assert k == pytest.approx(0.09546413502109694)


def test_kelly_fraction_zero_when_no_positive_return():
    # Цена равна payout (или выше) -> b <= 0 -> ставки нет.
    fee_pct = 2.0
    payout = 1 - fee_pct / 100
    assert kelly_fraction(0.9, payout, fee_pct=fee_pct) == 0.0
    assert kelly_fraction(0.9, payout + 0.01, fee_pct=fee_pct) == 0.0


def test_kelly_fraction_never_negative():
    # Даже при низкой fair_prob функция не должна уходить в минус.
    k = kelly_fraction(0.05, 0.50, fee_pct=2.0)
    assert k >= 0.0


def test_analyse_reference_case_is_value():
    v = analyse(REF_ODDS_A, REF_ODDS_B, REF_PRICE, fee_pct=REF_FEE)
    assert v.label == "value"
    assert v.fair_prob == pytest.approx(REF_FAIR_PROB)
    assert v.fair_price == pytest.approx(REF_FAIR_PROB * 100)
    assert v.net_edge == pytest.approx(0.09164556962025316)


def test_analyse_labels_skip_when_edge_non_positive():
    # Цена сильно выше справедливой -> net_edge <= 0.
    v = analyse(2.0, 2.0, 0.90, fee_pct=2.0)
    assert v.label == "skip"
    assert v.net_edge <= 0


def test_analyse_labels_thin_between_zero_and_threshold():
    # Подбираем цену так, чтобы net_edge был маленьким положительным.
    fair_prob = devig_two_way(2.0, 2.0)  # 0.5
    fee_pct = 2.0
    payout = 1 - fee_pct / 100
    fair_price = fair_prob * payout
    thin_price = fair_price - 0.001  # чуть дешевле справедливой -> маленький net edge
    v = analyse(2.0, 2.0, thin_price, fee_pct=fee_pct, thin_threshold=0.025)
    assert 0 < v.net_edge < 0.025
    assert v.label == "thin"
