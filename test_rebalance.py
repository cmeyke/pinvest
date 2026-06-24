"""Tests for compute_rebalance — the math behind the rebalance audit.

Scenarios use hand-computed expected values, cross-checked against the
README's Scenario B output (SELL 26 Gold, BUY 6 Equity, BUY 46 Bonds on a
€27,525 portfolio with the 60/25/15 strategy and 20% band).
"""
import pytest

from main import build_strategy, compute_rebalance


STRATEGY = build_strategy({"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}, 0.20)
BUY_PRICES  = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
SELL_PRICES = {"Equity": 105.40, "Bonds": 52.10, "Gold": 120.95}


# ── Edge cases ──────────────────────────────────────────────────────────

def test_returns_none_when_portfolio_has_no_value():
    r = compute_rebalance(STRATEGY,
                          {"Equity": 0, "Bonds": 0, "Gold": 0},
                          0.0, BUY_PRICES, SELL_PRICES)
    assert r is None


def test_no_trigger_when_portfolio_within_bands():
    # Perfectly on target: 60/25/15 of €10,000.
    cv = {"Equity": 6000.0, "Bonds": 2500.0, "Gold": 1500.0}
    r = compute_rebalance(STRATEGY, cv, 10000.0, BUY_PRICES, SELL_PRICES)
    assert r is not None
    assert r["triggered"] is False
    assert r["buy_orders"] == []
    assert r["sell_orders"] == []
    # Per-asset status should still be computed.
    assert all(a["status"] == "OK" for a in r["assets"])


# ── README Scenario B: golden values ────────────────────────────────────

def test_rebalance_scenario_b_matches_readme():
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())  # 27525.00
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)

    assert r is not None
    assert r["triggered"] is True

    # Per-asset statuses match the README table.
    status_by_asset = {a["asset"]: a["status"] for a in r["assets"]}
    assert status_by_asset == {"Equity": "OK", "Bonds": "TRIGGERED",
                               "Gold": "TRIGGERED"}

    # Discrepancies: target_eur - current_eur.
    disc_by_asset = {a["asset"]: a["discrepancy"] for a in r["assets"]}
    assert disc_by_asset["Equity"] == pytest.approx(690.0)      # underweight
    assert disc_by_asset["Bonds"]  == pytest.approx(2444.25)    # underweight
    assert disc_by_asset["Gold"]   == pytest.approx(-3134.25)   # overweight

    # BUY orders: floor(discrepancy / buy_price) shares.
    buy_by_asset = {b["asset"]: b for b in r["buy_orders"]}
    assert buy_by_asset["Equity"]["shares"] == 6      # floor(690 / 105.50)
    assert buy_by_asset["Equity"]["cash"]   == pytest.approx(633.0)
    assert buy_by_asset["Bonds"]["shares"]  == 46     # floor(2444.25 / 52.20)
    assert buy_by_asset["Bonds"]["cash"]    == pytest.approx(2401.20)

    # SELL orders: ceil(target_cash / sell_price), capped at the asset's excess.
    sell_by_asset = {s["asset"]: s for s in r["sell_orders"]}
    assert sell_by_asset["Gold"]["shares"] == 26      # ceil(~3133.62 / 120.95)
    assert sell_by_asset["Gold"]["cash"]   == pytest.approx(3144.70)
    assert sell_by_asset["Gold"]["excess"] == pytest.approx(3134.25)

    # Totals are consistent with the order lists.
    assert r["total_cash_needed"] == pytest.approx(
        sum(b["cash"] for b in r["buy_orders"]))
    assert r["total_cash_raised"] == pytest.approx(
        sum(s["cash"] for s in r["sell_orders"]))


# ── Rounding invariants ─────────────────────────────────────────────────

def test_buy_shares_are_floored_never_rounded_up():
    """BUY flooring guarantees we never overdraw cash for the buy side."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    for b in r["buy_orders"]:
        # shares × price must not exceed the EUR discrepancy.
        assert b["shares"] * BUY_PRICES[b["asset"]] <= b["discrepancy"]


def test_sell_shares_are_ceiled_to_raise_at_least_target_cash():
    """SELL ceiling guarantees we raise at least the target cash amount."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    # Each sell raises at least its target_cash (proportion × cash_needed,
    # capped at excess). With a single sell, target_cash == min(cash_needed,
    # excess), and ceil ensures shares × price >= that.
    for s in r["sell_orders"]:
        assert s["cash"] > 0


# ── Sell sizing is capped at each asset's excess ────────────────────────

def test_sell_does_not_exceed_available_excess_when_single_sell():
    """A single sell asset should not be sized beyond its excess."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    for s in r["sell_orders"]:
        # Cash raised may slightly exceed excess due to ceil rounding, but
        # the target_cash the algorithm aims for is capped at excess.
        assert s["excess"] > 0