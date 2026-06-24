"""Tests for print_portfolio_summary — valuation + per-asset breakdown.

Pure function (no input()): takes strategy, shares, prices dicts and
returns (current_values, total_value) while printing a human-readable
breakdown. Tests cover the math, the return-shape contract, and that the
output mentions each asset and the total.
"""
import pytest

from main import print_portfolio_summary


STRATEGY = {"Equity": {"target": 0.60, "lower": 0.48, "upper": 0.72},
            "Bonds":  {"target": 0.25, "lower": 0.20, "upper": 0.30},
            "Gold":   {"target": 0.15, "lower": 0.12, "upper": 0.18}}


def test_returns_current_values_and_total():
    shares = {"Equity": 150.0, "Bonds": 85.0, "Gold": 60.0}
    prices = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
    values, total = print_portfolio_summary(STRATEGY, shares, prices)

    assert values == {"Equity": 15825.0, "Bonds": 4437.0, "Gold": 7263.0}
    assert total == pytest.approx(27525.0)


def test_total_is_sum_of_current_values():
    shares = {"Equity": 150.0, "Bonds": 85.0, "Gold": 60.0}
    prices = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
    values, total = print_portfolio_summary(STRATEGY, shares, prices)
    assert total == pytest.approx(sum(values.values()))


def test_current_value_is_shares_times_price_per_asset():
    shares = {"Equity": 100.0, "Bonds": 200.0, "Gold": 50.0}
    prices = {"Equity": 10.0, "Bonds": 5.0, "Gold": 20.0}
    values, _ = print_portfolio_summary(STRATEGY, shares, prices)
    for asset in STRATEGY:
        assert values[asset] == pytest.approx(shares[asset] * prices[asset])


def test_handles_zero_shares():
    """A new portfolio with no holdings should produce zero values, not error."""
    shares = {"Equity": 0.0, "Bonds": 0.0, "Gold": 0.0}
    prices = {"Equity": 100.0, "Bonds": 50.0, "Gold": 100.0}
    values, total = print_portfolio_summary(STRATEGY, shares, prices)
    assert values == {"Equity": 0.0, "Bonds": 0.0, "Gold": 0.0}
    assert total == 0.0


def test_output_mentions_each_asset_and_total(capsys):
    """The human-readable breakdown should name every asset and the total."""
    shares = {"Equity": 150.0, "Bonds": 85.0, "Gold": 60.0}
    prices = {"Equity": 105.50, "Bonds": 52.20, "Gold": 121.05}
    print_portfolio_summary(STRATEGY, shares, prices)
    out = capsys.readouterr().out

    for asset in STRATEGY:
        assert asset in out
    assert "€27,525.00" in out   # total formatted with thousands separator


def test_iteration_follows_strategy_order(capsys):
    """Output rows should appear in the strategy dict's insertion order."""
    shares = {"Equity": 1.0, "Bonds": 1.0, "Gold": 1.0}
    prices = {"Equity": 1.0, "Bonds": 1.0, "Gold": 1.0}
    print_portfolio_summary(STRATEGY, shares, prices)
    out = capsys.readouterr().out
    # Equity row must come before Bonds, which comes before Gold.
    assert out.index("Equity") < out.index("Bonds")
    assert out.index("Bonds") < out.index("Gold")