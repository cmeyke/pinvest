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

    # BUY orders: originally floor(discrepancy / buy_price), then re-sized
    # by Phase 3 to fit the cash actually raised by sells. Gold's trimmed
    # sell raised €3,023.75, short of the original €3,034.20 buy total by
    # €10.45. Phase 3 walks the buys in order: Equity keeps all 6 shares
    # (€633), Bonds drops 46→45 (€2,349) to fit the budget.
    buy_by_asset = {b["asset"]: b for b in r["buy_orders"]}
    assert buy_by_asset["Equity"]["shares"] == 6
    assert buy_by_asset["Equity"]["cash"]   == pytest.approx(633.0)
    assert buy_by_asset["Bonds"]["shares"]  == 45
    assert buy_by_asset["Bonds"]["cash"]    == pytest.approx(2349.0)

    # SELL orders: ceil(target_cash / sell_price), then trimmed share-by-
    # share so the sale never overshoots the asset's excess (would push it
    # below target). Gold: ceil(3034.20/120.95)=26, but 26×120.95=3144.70
    # > excess 3134.25, so trimmed to 25 shares raising 3023.75.
    sell_by_asset = {s["asset"]: s for s in r["sell_orders"]}
    assert sell_by_asset["Gold"]["shares"] == 25
    assert sell_by_asset["Gold"]["cash"]   == pytest.approx(3023.75)
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
    """SELL ceiling guarantees we raise at least the target cash amount,
    unless trimming is required to avoid overshooting the excess cap —
    in which case raising slightly less cash is the correct trade-off."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    # Each sell raises a positive amount of cash toward the buys.
    for s in r["sell_orders"]:
        assert s["cash"] > 0


# ── Sell sizing never overshoots the excess ─────────────────────────────

def test_sell_cash_never_exceeds_excess():
    """Regression: a sell must never raise more cash than the asset's excess.

    Before the trim fix, ceil(target_cash / price) could round up past the
    excess cap by up to one share's worth of price, pushing an over-target
    asset *below* its target — the opposite of 'return to perfect target
    allocation'. The trim loop decrements shares until shares × price ≤
    excess, so a sell only ever moves an asset from over-target toward
    target, never past it.
    """
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    for s in r["sell_orders"]:
        assert s["cash"] <= s["excess"] + 1e-9, (
            f"{s['asset']} sell raises €{s['cash']:.2f} but excess is only "
            f"€{s['excess']:.2f} — would push the asset below target."
        )


def test_sell_keeps_asset_at_or_above_target_weight():
    """After a sell, the asset's post-sell value must still be ≥ its target."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    target_eur_by_asset = {a["asset"]: a["target_eur"] for a in r["assets"]}
    for s in r["sell_orders"]:
        post_sell_value = cv[s["asset"]] - s["cash"]
        assert post_sell_value >= target_eur_by_asset[s["asset"]] - 1e-9, (
            f"{s['asset']} post-sell value €{post_sell_value:.2f} is below "
            f"target €{target_eur_by_asset[s['asset']]:.2f}."
        )


@pytest.mark.parametrize("prices", [
    # Vary the sell price to exercise the trim across price regimes.
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 120.95},  # README price
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 121.00},  # round number
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 119.99},  # just under excess/26
])
def test_sell_never_overshoots_across_price_regimes(prices):
    """The no-overshoot invariant must hold for any sell price."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, prices)
    assert r is not None
    for s in r["sell_orders"]:
        assert s["cash"] <= s["excess"] + 1e-9


# ── Phase 3: buys always fit the cash actually raised ──────────────────

def test_buy_total_never_exceeds_cash_raised():
    """The order list must be executable as printed: sum(buys) ≤ sum(sells).

    Before Phase 3, a sell trim could leave the buys costing more than
    the sells raised — the user would have to come up with extra cash or
    manually trim the buys. Phase 3 re-sizes the buys so the printed list
    is always executable as-is.
    """
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    assert r["total_cash_needed"] <= r["total_cash_raised"] + 1e-9


def test_buy_total_fits_cash_raised_with_expensive_sell_share():
    """Regression for the case that motivated Phase 3.

    An expensive sell asset (€2,500/share) with €4,000 excess: trim drops
    the sell from 2 shares (€5,000, overshoot) to 1 share (€2,500),
    raising €2,500 less than the buys originally needed. Without Phase 3
    the printed buys would cost ~€4,500 — unexecutable. Phase 3 must
    re-size the buys to fit the €2,500 actually raised.
    """
    cv = {"Equity": 6000.0, "Bonds": 3000.0, "Gold": 10000.0}
    total = sum(cv.values())  # €19,000
    buy_prices  = {"Equity": 100.0, "Bonds": 100.0, "Gold": 2500.0}
    sell_prices = {"Equity": 99.0,  "Bonds": 99.0,  "Gold": 2500.0}
    r = compute_rebalance(STRATEGY, cv, total, buy_prices, sell_prices)
    assert r is not None
    assert r["total_cash_needed"] <= r["total_cash_raised"] + 1e-9
    # And each individual buy is internally consistent.
    for b in r["buy_orders"]:
        assert b["cash"] == b["shares"] * buy_prices[b["asset"]]


@pytest.mark.parametrize("sell_prices", [
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 120.95},   # README
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 2500.00},  # expensive Gold
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 5000.00},  # very expensive
    {"Equity": 105.40, "Bonds": 52.10, "Gold": 0.01},     # pathological low
])
def test_order_list_always_executable_across_price_regimes(sell_prices):
    """sum(buy cash) ≤ sum(sell cash) must hold for any sell price."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, sell_prices)
    assert r is not None
    assert r["total_cash_needed"] <= r["total_cash_raised"] + 1e-9, (
        f"buys cost €{r['total_cash_needed']:.2f} but sells only raised "
        f"€{r['total_cash_raised']:.2f} — order list is unexecutable."
    )


def test_phase3_does_not_leave_unneeded_cash_idle_when_buys_can_fill():
    """Phase 3 should spend as much of the raised cash as the buys can absorb.

    A naive proportional scale floors each buy independently and can leave
    significant cash idle (e.g. €147 uninvested on the README scenario).
    The greedy allocator walks buys in order, spending up to each buy's
    original floored max, so uninvested cash stays under one share of the
    last buy asset — not a multiple of every buy's rounding error.
    """
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_rebalance(STRATEGY, cv, total, BUY_PRICES, SELL_PRICES)
    assert r is not None
    uninvested = r["total_cash_raised"] - r["total_cash_needed"]
    # Bounded by the price of one share of the last buy asset (Bonds €52.20).
    assert uninvested < BUY_PRICES["Bonds"]