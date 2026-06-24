"""Tests for compute_lump_sum — the smart cash-injection math.

Scenarios use hand-computed expected values, cross-checked against the
README's Scenario A output (Equity 12 shares €1,314.16, Bonds 32 shares
€1,685.84, Gold 0 shares, leftover €63.60) on a €27,525 portfolio with
the 60/25/15 strategy and a €3,000 lump sum.
"""
import pytest

from main import build_strategy, compute_lump_sum


STRATEGY = build_strategy({"Equity": 0.60, "Bonds": 0.25, "Gold": 0.15}, 0.20)
BUY_PRICES = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}


# ── README Scenario A: golden values ────────────────────────────────────

def test_lump_sum_scenario_a_matches_readme():
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())  # 27525.00
    r = compute_lump_sum(STRATEGY, cv, total, 3000.0, BUY_PRICES)

    # New target total = existing + lump sum.
    assert r["new_target"] == pytest.approx(30525.0)

    # Deficits: ideal at new target weight minus current value, clamped ≥ 0.
    # Equity ideal = 30525 * 0.60 = 18315 → deficit = 18315 - 15825 = 2490
    # Bonds  ideal = 30525 * 0.25 = 7631.25 → deficit = 7631.25 - 4437 = 3194.25
    # Gold   ideal = 30525 * 0.15 = 4578.75 → current 7263 is above → deficit 0
    assert r["deficits"]["Equity"] == pytest.approx(2490.0)
    assert r["deficits"]["Bonds"]  == pytest.approx(3194.25)
    assert r["deficits"]["Gold"]   == pytest.approx(0.0)
    assert r["total_deficit"]      == pytest.approx(5684.25)

    # Cash routed pro-rata by deficit: Equity 2490/5684.25 * 3000 = 1314.16
    # Bonds 3194.25/5684.25 * 3000 = 1685.84. Gold gets 0.
    assert r["allocated"]["Equity"] == pytest.approx(1314.16, abs=0.01)
    assert r["allocated"]["Bonds"]  == pytest.approx(1685.84, abs=0.01)
    assert r["allocated"]["Gold"]   == pytest.approx(0.0)

    # Integer-share orders: floor(cash / price).
    orders = {o["asset"]: o for o in r["orders"]}
    assert orders["Equity"]["shares"] == 12    # floor(1314.16 / 105.50)
    assert orders["Equity"]["spent"]  == pytest.approx(1266.0)
    assert orders["Bonds"]["shares"]  == 32    # floor(1685.84 / 52.20)
    assert orders["Bonds"]["spent"]   == pytest.approx(1670.4)
    assert orders["Gold"]["shares"]   == 0

    # Uninvested leftover from integer-share rounding.
    assert r["total_leftover"] == pytest.approx(63.60, abs=0.01)


# ── Allocation invariants ───────────────────────────────────────────────

def test_allocated_cash_sums_to_lump_sum():
    """All of the lump sum must be routed somewhere (never dropped)."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    for lump in (100.0, 3000.0, 500_000.0):
        r = compute_lump_sum(STRATEGY, cv, total, lump, BUY_PRICES)
        assert sum(r["allocated"].values()) == pytest.approx(lump)


def test_above_target_assets_receive_no_cash_when_deficits_exist():
    """Gold is above target → must receive €0 in the deficit-pro-rata branch."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_lump_sum(STRATEGY, cv, total, 3000.0, BUY_PRICES)
    assert r["allocated"]["Gold"] == 0.0
    assert r["deficits"]["Gold"] == 0.0


# ── Rounding invariant ──────────────────────────────────────────────────

def test_buy_shares_are_floored_so_spent_never_exceeds_allocated_cash():
    """floor() guarantees we never spend more than the allocated cash."""
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_lump_sum(STRATEGY, cv, total, 3000.0, BUY_PRICES)
    for o in r["orders"]:
        assert o["spent"] <= o["cash"] + 1e-9
        assert o["leftover"] >= -1e-9


def test_total_leftover_equals_sum_of_per_order_leftovers():
    cv = {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    total = sum(cv.values())
    r = compute_lump_sum(STRATEGY, cv, total, 3000.0, BUY_PRICES)
    assert r["total_leftover"] == pytest.approx(
        sum(o["leftover"] for o in r["orders"]))


# ── Note on the unreachable "split by target weight" branch ─────────────
# compute_lump_sum has a defensive `else` branch that splits the lump sum
# by target weight when total_deficit == 0. With targets summing to 1.0
# and lump_sum > 0, new_target = total + lump > total, so at least one
# asset's ideal exceeds its current value → total_deficit > 0 always. The
# branch is unreachable under the strategy invariant (sum of targets = 1)
# enforced by build_strategy. No test covers it; a future refactor could
# drop it or assert it's unreachable.