"""Tests for the leg-aware pricing functions in main.py.

These functions pick the price used for valuation vs. order sizing:
- resolve_price    → fair value (midprice) for valuation and band-breach
- resolve_buy_price → ask-based, for sizing BUY orders (you pay the ask)
- resolve_sell_price → bid-based, for sizing SELL orders (you receive the bid)

The financially-critical invariant is the bid/ask asymmetry: buy and sell
prices must never default to the midprice when the corresponding side is
quoted, otherwise order sizing would systematically under/over-shoot.
"""
import pytest

from main import resolve_price, resolve_buy_price, resolve_sell_price


def quote(**overrides) -> dict:
    """Build a quote dict with all keys defaulting to None."""
    base = {"bid": None, "ask": None, "last": None, "close": None,
            "symbol": "TEST", "spread_pct": None}
    base.update(overrides)
    return base


# ── resolve_price: fair-value fallback chain ────────────────────────────

@pytest.mark.parametrize("bid,ask,expected", [
    (100.0, 102.0, 101.0),   # midprice when both sides quoted
    (100.0, None,  100.0),   # bid-only
    (None,  102.0,  102.0),  # ask-only
])
def test_resolve_price_uses_quote_sides(bid, ask, expected):
    assert resolve_price(quote(bid=bid, ask=ask)) == pytest.approx(expected)


@pytest.mark.parametrize("last,close,expected", [
    (99.0, 98.0, 99.0),   # last beats close
    (None, 98.0, 98.0),   # close when no last
])
def test_resolve_price_falls_back_to_last_then_close(last, close, expected):
    q = quote(bid=None, ask=None, last=last, close=close)
    assert resolve_price(q) == pytest.approx(expected)


def test_resolve_price_returns_none_when_no_data():
    assert resolve_price(quote()) is None


def test_resolve_price_prefers_midprice_over_last():
    # Even when last is present, a quoted book wins.
    assert resolve_price(quote(bid=100.0, ask=102.0, last=99.0)) == pytest.approx(101.0)


# ── resolve_buy_price: ask-based sizing ─────────────────────────────────

def test_buy_price_uses_ask_when_available():
    assert resolve_buy_price(quote(bid=100.0, ask=102.0)) == pytest.approx(102.0)


def test_buy_price_never_uses_midprice_when_ask_available():
    """Critical invariant: BUY sizing must not use the cheaper midprice."""
    q = quote(bid=100.0, ask=102.0)
    buy = resolve_buy_price(q)
    mid = resolve_price(q)
    assert buy is not None and mid is not None
    assert buy > mid


def test_buy_price_falls_back_to_fair_value_chain():
    # No ask → midprice (both sides would be needed), then bid, last, close.
    assert resolve_buy_price(quote(bid=100.0, ask=None)) == pytest.approx(100.0)
    assert resolve_buy_price(quote(bid=None, ask=None, last=99.0)) == pytest.approx(99.0)
    assert resolve_buy_price(quote(bid=None, ask=None, close=98.0)) == pytest.approx(98.0)


def test_buy_price_returns_none_when_no_data():
    assert resolve_buy_price(quote()) is None


# ── resolve_sell_price: bid-based sizing ────────────────────────────────

def test_sell_price_uses_bid_when_available():
    assert resolve_sell_price(quote(bid=100.0, ask=102.0)) == pytest.approx(100.0)


def test_sell_price_never_uses_midprice_when_bid_available():
    """Critical invariant: SELL sizing must not use the richer midprice."""
    q = quote(bid=100.0, ask=102.0)
    sell = resolve_sell_price(q)
    mid = resolve_price(q)
    assert sell is not None and mid is not None
    assert sell < mid


def test_sell_price_falls_back_to_fair_value_chain():
    # No bid → midprice (both sides needed), then ask, last, close.
    assert resolve_sell_price(quote(bid=None, ask=102.0)) == pytest.approx(102.0)
    assert resolve_sell_price(quote(bid=None, ask=None, last=99.0)) == pytest.approx(99.0)
    assert resolve_sell_price(quote(bid=None, ask=None, close=98.0)) == pytest.approx(98.0)


def test_sell_price_returns_none_when_no_data():
    assert resolve_sell_price(quote()) is None


# ── Spread asymmetry: buy ≥ sell (you cross the spread) ─────────────────

def test_buy_price_is_at_least_sell_price_when_both_sides_quoted():
    """Crossing the spread: a round-trip never profits at the midprice."""
    q = quote(bid=100.0, ask=102.0)
    buy = resolve_buy_price(q)
    sell = resolve_sell_price(q)
    assert buy is not None and sell is not None
    assert buy >= sell